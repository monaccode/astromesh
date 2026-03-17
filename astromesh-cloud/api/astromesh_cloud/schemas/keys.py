from datetime import datetime
from pydantic import BaseModel

class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["agent:run"]

class ApiKeyResponse(BaseModel):
    id: str
    prefix: str
    name: str
    scopes: list[str]
    created_at: datetime
    model_config = {"from_attributes": True}

class ApiKeyCreated(ApiKeyResponse):
    key: str

class ProviderKeyCreate(BaseModel):
    provider: str
    key: str

class ProviderKeyResponse(BaseModel):
    id: str
    provider: str
    created_at: datetime
    model_config = {"from_attributes": True}
