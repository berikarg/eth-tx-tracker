from decimal import Decimal

from pydantic import BaseModel, field_validator, Field
from typing import Optional
from eth_utils import is_checksum_address

class TrackRequest(BaseModel):
    address: str
    contract_address: Optional[str] = None  # If None => ETH
    amount: Decimal = Field(gt=0)

    @field_validator('address', mode='after')
    @classmethod
    def validate_address(cls, v):
        if not v.lower().startswith("0x"):
            raise ValueError("Ethereum address must start with '0x'.")
        if not is_checksum_address(v):
            raise ValueError("Ethereum address must be in checksum format.")
        return v
