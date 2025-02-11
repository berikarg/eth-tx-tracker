import logging
import asyncio
import traceback
from typing import List
from decimal import Decimal

from web3 import Web3, AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider
from web3.types import BlockData, TxData
from eth_typing import ChecksumAddress

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


class TrackService:
    def __init__(self, repository: TrackRepository, eth_rpc_url: str, logger: logging.Logger):
        self.repository = repository
        self.web3 = AsyncWeb3(AsyncHTTPProvider(eth_rpc_url))
        self.logger = logger
        self._last_processed_block = 0

    def create_track(self, req: TrackRequest) -> Track:
        address = self.web3.to_checksum_address(req.address)
        contract_address = (
            self.web3.to_checksum_address(req.contract_address)
            if req.contract_address
            else None
        )
        track = Track(address=address, amount=req.amount, contract_address=contract_address)
        self.repository.add_track(track)
        return track

    def list_tracks(self) -> List[Track]:
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

            except Exception as e:
                self.logger.error(f"Error in block listener: {traceback.format_exc()}")
                await asyncio.sleep(5)

    async def _process_block(self, block: BlockData) -> None:
        tracks = self.repository.list_tracks()
        if not tracks:
            return

        block_number = block["number"]
        transactions = block["transactions"]

        # 1) Find ETH transfers (updates tracks in-place)
        self._find_eth_transfers(transactions, tracks, block_number)

        # 2) For ERC-20, build a set of contract addresses we track
        contract_addresses = list({self.web3.to_checksum_address(t.contract_address.lower())
                                   for t in tracks if t.contract_address})

        if contract_addresses:
            await self._process_erc20_logs(block_number, contract_addresses, tracks)


    def _find_eth_transfers(
        self, transactions: List[TxData], tracks: List[Track], block_number: int
    ) -> None:
        """
        Looks for ETH transfers matching any track. Updates `track.is_found`
        if an exact match is found. (No return value; modifies in place.)
        """
        eth_tracks = [t for t in tracks if t.contract_address is None and not t.is_found]
        if not eth_tracks:
            return

        for tx in transactions:
            to_addr = tx["to"]
            value_wei = tx["value"]
            tx_hash = tx["hash"].hex()

            if not to_addr:
                continue
            for track in eth_tracks:
                # Compare addresses
                if to_addr.lower() != track.address.lower():
                    continue
                    # Wei -> ETH
                eth_value = Decimal(value_wei) / Decimal(10 ** 18)
                if eth_value == track.amount:
                    self.logger.info(
                        f"[Block {block_number}] Found ETH transfer {eth_value} to {to_addr}, tx={tx_hash}"
                    )
                    track.mark_found()


    async def _process_erc20_logs(self, block_num: int, contract_addresses: List[ChecksumAddress], tracks):
        """
        Use `eth_getLogs` to get only Transfer events for the specified addresses in this block.
        """

        logs = await self.web3.eth.get_logs({
            "fromBlock": block_num,
            "toBlock": block_num,
            "address": contract_addresses,
            "topics": [TRANSFER_TOPIC],
        })

        if not logs:
            return

        for log_entry in logs:
            # log_entry["address"] is the contract that emitted Transfer
            contract_address = log_entry["address"].lower()

            # Filter tracks for that contract (and not found yet)
            matching_tracks = [
                t for t in tracks
                if t.contract_address and t.contract_address.lower() == contract_address and not t.is_found
            ]
            if not matching_tracks:
                continue

            contract = self.web3.eth.contract(address=log_entry["address"], abi=ERC20_ABI)
            parsed_event = contract.events.Transfer().process_log(log_entry)

            from_address = parsed_event.args["from"]
            to_address = parsed_event.args["to"]
            value_raw = parsed_event.args["value"]

            decimals = await contract.functions.decimals().call()
            value_human = Decimal(value_raw) / Decimal(10 ** decimals)

            for track in matching_tracks:
                if to_address.lower() == track.address.lower() and value_human == track.amount:
                    self.logger.info(
                        f"Found ERC-20 Transfer: contract={contract_address}, block={block_num}, "
                        f"from={from_address}, to={to_address}, amount={value_human}"
                    )
                    track.mark_found()