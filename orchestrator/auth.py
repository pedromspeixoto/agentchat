from fastapi import HTTPException, Request
from .config import settings

def bearer_auth(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.removeprefix("Bearer ")
    if token != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token
