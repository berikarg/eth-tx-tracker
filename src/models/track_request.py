from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

class TrackRequest(BaseModel):
    address: str
    contract_address: Optional[str] = None  # If None => ETH
    amount: Decimal