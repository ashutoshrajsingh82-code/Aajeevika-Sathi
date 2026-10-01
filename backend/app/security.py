"""Password hashing and signed-cookie role checks for staff accounts."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .config import AUTH_COOKIE_NAME, AUTH_COOKIE_HOURS, AUTH_SECRET,DEMO_ADMIN_USERNAME,DEMO_ADMIN_PASSWORD,DEMO_COUNSELLOR_USERNAME,DEMO_COUNSELLOR_PASSWORD
from .db import get_db
from .models import AuthUser

PBKDF2_ITERATIONS=310_000

def _b64(data:bytes)->str:return base64.urlsafe_b64encode(data).decode().rstrip("=")
def _unb64(value:str)->bytes:return base64.urlsafe_b64decode(value+"="*((4-len(value)%4)%4))

def hash_password(password:str)->str:
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}"

def verify_password(password:str,encoded:str)->bool:
    try:
        scheme,iterations,salt,digest=encoded.split("$",3)
        if scheme!="pbkdf2_sha256":return False
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),_unb64(salt),int(iterations))
        return hmac.compare_digest(candidate,_unb64(digest))
    except (ValueError,TypeError):return False

def authenticate(db:Session,username:str,password:str)->AuthUser|None:
    user=db.query(AuthUser).filter_by(username=username,active=True).one_or_none()
    if user:
        return user if verify_password(password,user.password_hash) else None
    # Match the work of a real password verification for unknown usernames.
    hashlib.pbkdf2_hmac("sha256",password.encode(),b"aajeevika-login-salt",PBKDF2_ITERATIONS)
    return None

def ensure_demo_accounts(db:Session)->None:
    if DEMO_ADMIN_USERNAME==DEMO_COUNSELLOR_USERNAME:raise RuntimeError("Demo admin and counsellor usernames must be different")
    for username,password,role in ((DEMO_ADMIN_USERNAME,DEMO_ADMIN_PASSWORD,"admin"),(DEMO_COUNSELLOR_USERNAME,DEMO_COUNSELLOR_PASSWORD,"counsellor")):
        user=db.query(AuthUser).filter_by(username=username).one_or_none()
        if user is None:db.add(AuthUser(username=username,password_hash=hash_password(password),role=role,active=True))
        elif user.role!=role:raise RuntimeError(f"Demo account {username!r} already exists with another role")
        elif not verify_password(password,user.password_hash):user.password_hash=hash_password(password);user.auth_version+=1
    db.commit()

def issue_token(user:AuthUser)->str:
    payload=_b64(json.dumps({"sub":user.id,"role":user.role,"ver":user.auth_version,"exp":int(time.time()+AUTH_COOKIE_HOURS*3600)},separators=(",",":")).encode())
    signature=_b64(hmac.new(AUTH_SECRET.encode(),payload.encode(),hashlib.sha256).digest())
    return f"{payload}.{signature}"

def verify_token(token:str,db:Session)->dict:
    try:
        payload,signature=token.split(".",1)
        expected=_b64(hmac.new(AUTH_SECRET.encode(),payload.encode(),hashlib.sha256).digest())
        if not secrets.compare_digest(signature,expected):raise ValueError("signature")
        data=json.loads(_unb64(payload))
        if int(data["exp"])<=int(time.time()):raise ValueError("expired")
        user=db.get(AuthUser,int(data["sub"]))
        if not user or not user.active or user.role!=data["role"] or user.auth_version!=int(data["ver"]):raise ValueError("account")
        return {"username":user.username,"role":user.role}
    except (ValueError,KeyError,TypeError,json.JSONDecodeError,UnicodeDecodeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Sign in to continue",headers={"WWW-Authenticate":"Cookie"})

def current_staff(token:str|None=Cookie(default=None,alias=AUTH_COOKIE_NAME),db:Session=Depends(get_db)):
    if not token:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Sign in to continue")
    return verify_token(token,db)

def require_roles(*roles:str):
    def dependency(staff:dict=Depends(current_staff)):
        if staff["role"] not in roles:raise HTTPException(status.HTTP_403_FORBIDDEN,"Your account cannot access this page")
        return staff
    return dependency

