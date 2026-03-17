from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from astromesh_cloud.services.auth_service import verify_token

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = verify_token(credentials.credentials)
        return {"user_id": payload["sub"], "email": payload["email"]}
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
