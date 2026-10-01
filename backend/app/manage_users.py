"""Manage staff accounts without putting passwords in shell history."""
import argparse
from getpass import getpass
from .db import SessionLocal
from .models import AuthUser
from .security import hash_password

def password_pair()->str:
    first=getpass("Password (12+ characters): ")
    second=getpass("Repeat password: ")
    if len(first)<12:raise SystemExit("Password must contain at least 12 characters.")
    if first!=second:raise SystemExit("Passwords did not match.")
    return first

def main():
    parser=argparse.ArgumentParser(description="Create and maintain counsellor/admin accounts")
    commands=parser.add_subparsers(dest="command",required=True)
    add=commands.add_parser("add-user");add.add_argument("--username",required=True);add.add_argument("--role",required=True,choices=("admin","counsellor"))
    reset=commands.add_parser("set-password");reset.add_argument("--username",required=True)
    disable=commands.add_parser("disable-user");disable.add_argument("--username",required=True)
    args=parser.parse_args();db=SessionLocal()
    try:
        user=db.query(AuthUser).filter_by(username=args.username).one_or_none()
        if args.command=="add-user":
            if user:raise SystemExit("That username already exists.")
            user=AuthUser(username=args.username,role=args.role,password_hash=hash_password(password_pair()),active=True)
            db.add(user);db.commit();print(f"Created {args.role} account {args.username}.")
        elif user is None:raise SystemExit("User not found.")
        elif args.command=="set-password":
            user.password_hash=hash_password(password_pair());user.auth_version+=1;db.commit();print(f"Updated password for {args.username}; active sessions were revoked.")
        elif args.command=="disable-user":
            user.active=False;user.auth_version+=1;db.commit();print(f"Disabled {args.username}; active sessions were revoked.")
    finally:db.close()

if __name__=="__main__":main()
