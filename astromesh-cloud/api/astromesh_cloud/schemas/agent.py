from datetime import datetime
from pydantic import BaseModel, Field

class WizardConfig(BaseModel):
    name: str = Field(max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(max_length=255)
    system_prompt: str
    tone: str = "professional"
    model: str
    routing_strategy: str = "cost_optimized"
    tools: list[str] = []
    tool_configs: dict[str, dict] = {}
    memory_enabled: bool = False
    pii_filter: bool = False
    content_filter: bool = False
    orchestration: str = "react"

class AgentCreate(BaseModel):
    config: WizardConfig

class AgentUpdate(BaseModel):
    config: WizardConfig

class AgentResponse(BaseModel):
    id: str
    name: str
    display_name: str
    status: str
    config: dict
    runtime_name: str
    created_at: datetime
    updated_at: datetime
    deployed_at: datetime | None = None
    model_config = {"from_attributes": True}

class AgentListItem(BaseModel):
    id: str
    name: str
    display_name: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}
