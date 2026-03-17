from pydantic import BaseModel

class OAuthCallback(BaseModel):
    code: str
    redirect_uri: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str | None = None
    auth_provider: str
    model_config = {"from_attributes": True}
