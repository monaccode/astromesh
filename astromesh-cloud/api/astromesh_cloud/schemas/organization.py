from pydantic import BaseModel

class OrgResponse(BaseModel):
    id: str
    slug: str
    name: str
    model_config = {"from_attributes": True}

class OrgUpdate(BaseModel):
    name: str

class MemberInvite(BaseModel):
    email: str

class MemberResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
