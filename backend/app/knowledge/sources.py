"""Allowlisted official source registry and SSRF-resistant fetch helpers."""
from pathlib import Path
import ipaddress,json,socket
from urllib.parse import urlparse
import httpx

REGISTRY_PATH=Path(__file__).with_name("sources.json")
def registry():return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
def approved_hosts():return set(registry()["approved_hosts"])

def official_url(url:str)->bool:
    try:
        parsed=urlparse(url)
        if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:return False
        if parsed.port not in (None,443):return False
        host=parsed.hostname.rstrip(".").lower()
        return any(host==domain or host.endswith("."+domain) for domain in approved_hosts())
    except (ValueError,TypeError):return False

def safe_public_host(url:str):
    if not official_url(url):raise ValueError("Only HTTPS URLs from the configured government-source registry can be fetched")
    host=urlparse(url).hostname
    for item in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
        address=ipaddress.ip_address(item[4][0])
        if not address.is_global:raise ValueError("Government source resolved to a non-public network address")

def download_official(url:str,*,transport=None,max_bytes:int=20*1024*1024)->tuple[bytes,str]:
    current=url
    for _ in range(4):
        safe_public_host(current)
        with httpx.Client(timeout=30,follow_redirects=False,transport=transport) as client:
            response=client.get(current)
        if response.status_code in {301,302,303,307,308}:
            location=response.headers.get("location")
            if not location:raise ValueError("Source redirect did not include a location")
            current=str(response.url.join(location))
            continue
        response.raise_for_status()
        if len(response.content)>max_bytes:raise ValueError("Source exceeds the 20 MB download limit")
        return response.content,response.headers.get("content-type","")
    raise ValueError("Too many redirects while downloading government source")
