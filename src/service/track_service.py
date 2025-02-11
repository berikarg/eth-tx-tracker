import logging
import asyncio
import traceback
from typing import List, Set
from decimal import Decimal
from dataclasses import dataclass

from web3 import Web3, AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from web3.types import BlockData, TxData, LogReceipt
from web3.exceptions import ContractLogicError, ABIEventNotFound, ABIFunctionNotFound, BadFunctionCallOutput

from src.repository.track_repository import TrackRepository
from src.models.track import Track
from src.models.track_request import TrackRequest

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]
TRANSFER_TOPIC = "0x" + Web3.keccak(text="Transfer(address,address,uint256)").hex()

@dataclass(frozen=True)
class FoundTransfer:
    track: Track
    tx_hash: str

class TrackAlreadyExistsError(Exception):
    def __init__(self, track: Track):
        self.message = (f"Tracking request for address {track.address} amount {track.amount} "
                        f"contract {track.contract_address} already exists.")
        super().__init__(self.message)

def find_eth_transfers(
    transactions: List[TxData],
    tracks: Set[Track]
) -> List[FoundTransfer]:
    """
    Looks for ETH transfers matching any track. Returns a list of FoundTransfer objects.
    """
    eth_tracks = [t for t in tracks if t.contract_address is None]
    if not eth_tracks:
        return []

    found_transfers: List[FoundTransfer] = []
    for tx in transactions:
        to_addr = tx["to"]
        value_wei = tx["value"]
        tx_hash = tx["hash"].hex()

        if not to_addr:
            continue

        for track in eth_tracks:
            if to_addr.lower() == track.address.lower():
                eth_value = Decimal(value_wei) / Decimal(10**18)
                if eth_value == track.amount:
                    found_transfers.append(FoundTransfer(track=track, tx_hash=tx_hash))

    return found_transfers


class TrackService:
    def __init__(self, repository: TrackRepository, eth_rpc_url: str, logger: logging.Logger):
        self.repository = repository
        self.web3 = AsyncWeb3(AsyncHTTPProvider(eth_rpc_url))
        self.logger = logger
        self._last_processed_block = 0

    async def create_track(self, req: TrackRequest) -> Track:
        address = self.web3.to_checksum_address(req.address)
        try:
            contract_address = (
                self.web3.to_checksum_address(req.contract_address)
                if req.contract_address
                else None
            )
        except ValueError:
            raise ValueError("The provided contract address is not valid")
        decimals = 18  # Default for ETH, will be requested for tokens

        # If a contract address is provided, check its validity as an ERC20 contract
        if contract_address is not None:
            # Check if contract has 'decimals' function and 'Transfer' event
            try:
                contract = self.web3.eth.contract(address=contract_address, abi=ERC20_ABI)
                decimals = await contract.functions.decimals().call()

                transfer_event = contract.events.Transfer
                if not transfer_event:
                    raise ValueError("The provided contract does not have a 'Transfer' event")

            except (ContractLogicError, ABIEventNotFound, ABIFunctionNotFound, BadFunctionCallOutput):
                raise ValueError("The provided contract is not a valid ERC20 contract")

        track = Track(address=address, amount=req.amount, decimals=decimals, contract_address=contract_address)

        if self.repository.exists(track):
            raise TrackAlreadyExistsError(track)

        self.repository.add_track(track)
        return track

    def list_tracks(self) -> Set[Track]:
        return self.repository.list_tracks()

    async def start_block_listener(self) -> None:
        # Get the latest block at startup
        self._last_processed_block = await self.web3.eth.block_number
        self.logger.info(f"Starting block listener from block {self._last_processed_block}")

        while True:
            try:
                current_block = await self.web3.eth.block_number
                if current_block > self._last_processed_block:
                    for block_num in range(self._last_processed_block + 1, current_block + 1):
                        self.logger.info(f"Checking block {block_num}")
                        block = await self.web3.eth.get_block(block_num, full_transactions=True)
                        await self._process_block(block)
                    self._last_processed_block = current_block
                await asyncio.sleep(1)

            except Exception:
                self.logger.error(f"Error in block listener: {traceback.format_exc()}")
                await asyncio.sleep(5)

    async def _process_block(self, block: BlockData) -> None:
        tracks = self.repository.list_tracks()
        if not tracks:
            return

        block_number = block["number"]
        transactions = block["transactions"]

        found_transfers = find_eth_transfers(transactions, tracks)
        for ft in found_transfers:
            self.logger.info(
                f"Found ETH Transfer: block={block_number}, "
                f"to={ft.track.address}, amount={ft.track.amount}, tx=0x{ft.tx_hash}"
            )
            self.repository.remove_track(ft.track)

        # For ERC-20, build a set of contract addresses we track
        contract_addresses = list({self.web3.to_checksum_address(t.contract_address.lower())
                                   for t in tracks if t.contract_address})
        if not contract_addresses:
            return

        logs = await self.web3.eth.get_logs({
            "fromBlock": block_number,
            "toBlock": block_number,
            "address": contract_addresses,
            "topics": [TRANSFER_TOPIC],
        })

        found_transfers = self.process_erc20_logs(logs, tracks)
        for ft in found_transfers:
            self.logger.info(
                f"Found ERC-20 Transfer: block={block_number}, "
                f"to={ft.track.address}, amount={ft.track.amount}, tx=0x{ft.tx_hash}, contract={ft.track.contract_address}"
            )
            self.repository.remove_track(ft.track)

    def process_erc20_logs(
            self,
            logs: List[LogReceipt],
            tracks: Set[Track]
    ) -> List[FoundTransfer]:
        if not logs:
            return []

        found_transfers = []

        for log_entry in logs:
            # log_entry["address"] is the contract that emitted Transfer
            contract_address = log_entry["address"].lower()

            # Filter tracks for that contract
            matching_tracks = [
                t for t in tracks
                if t.contract_address and t.contract_address.lower() == contract_address
            ]
            if not matching_tracks:
                continue

            contract = self.web3.eth.contract(address=log_entry["address"], abi=ERC20_ABI)
            parsed_event = contract.events.Transfer().process_log(log_entry)

            to_address = parsed_event.args["to"]
            value_raw = parsed_event.args["value"]

            for track in matching_tracks:
                if to_address.lower() != track.address.lower():
                    continue
                value_human = Decimal(value_raw) / Decimal(10 ** track.decimals)
                if value_human == track.amount:
                    found_transfers.append(FoundTransfer(track=track, tx_hash=log_entry["transactionHash"].hex()))
        return found_transfers
