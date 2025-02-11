from typing import Optional
from decimal import Decimal

class Track:
    def __init__(self, address: str, amount: Decimal, decimals: int, contract_address: Optional[str] = None):
        self.address = address
        self.amount = amount
        self.contract_address = contract_address
        self.decimals = decimals

    def __eq__(self, other):
        if not isinstance(other, Track):
            return NotImplemented
        return (self.address == other.address and
                self.amount == other.amount and
                self.decimals == other.decimals and
                self.contract_address == other.contract_address)

    def __hash__(self):
        return hash((self.address, self.amount, self.decimals, self.contract_address))