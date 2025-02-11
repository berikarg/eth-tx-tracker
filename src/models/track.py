from typing import Optional
from decimal import Decimal

class Track:
    def __init__(self, address: str, amount: Decimal, contract_address: Optional[str] = None):
        self.address = address
        self.amount = amount
        self.contract_address = contract_address
        self.is_found = False

    def mark_found(self):
        self.is_found = True