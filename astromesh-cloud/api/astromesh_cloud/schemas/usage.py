from decimal import Decimal
from pydantic import BaseModel

class UsageSummary(BaseModel):
    total_requests: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: Decimal
    period_start: str
    period_end: str
