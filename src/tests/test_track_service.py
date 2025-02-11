import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.models.track import Track
from src.service.track_service import TrackService, find_eth_transfers, FoundTransfer


@pytest.mark.parametrize(
    "description,transactions,tracks,expected_tracks",
    [
        (
            "No transactions => no track found",
            [],
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
            set(),
        ),
        (
            "Transaction with missing 'to' => skip it",
            [
                {
                    "to": None,
                    "value": int(1 * 10**18),
                    "hash": b"\x01"  # dummy bytes for hash
                }
            ],
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
            set(),
        ),
        (
            "Transaction to a different address => no match",
            [
                {
                    "to": "0xdef",
                    "value": int(1 * 10**18),
                    "hash": b"\x02"
                }
            ],
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
            set(),
        ),
        (
            "Transaction has correct address but value doesn't match => no find",
            [
                {
                    "to": "0xAbC",  # ignoring case
                    "value": int(2 * 10**18),  # 2.0 ETH
                    "hash": b"\x03"
                }
            ],
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
            set(),
        ),
        (
            "Transaction matches address and value => track found",
            [
                {
                    "to": "0xabc",
                    "value": int(1 * 10**18),
                    "hash": b"\x04"
                }
            ],
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
            {Track(address="0xabc", amount=Decimal("1.0"), decimals=18)},
        ),
        (
            "Two transactions, one matches track",
            [
                {"to": "0x111", "value": 10**18, "hash": b"\x05"},  # mismatch
                {"to": "0xabc", "value": int(3 * 10**18), "hash": b"\x06"},  # match
            ],
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18)},
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18)},
        ),
        (
            "Two transactions, both match",
            [
                {"to": "0x111", "value": 10 ** 18, "hash": b"\x05"},
                {"to": "0xabc", "value": int(3 * 10 ** 18), "hash": b"\x06"},
            ],
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18), Track(address="0x111", amount=Decimal("1.0"), decimals=18)},
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18), Track(address="0x111", amount=Decimal("1.0"), decimals=18)},
        ),
(
            "One transaction, two tracks, one match",
            [
                {"to": "0xabc", "value": int(3 * 10 ** 18), "hash": b"\x06"},  # match
            ],
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18), Track(address="0x111", amount=Decimal("1.0"), decimals=18)},
            {Track(address="0xabc", amount=Decimal("3.0"), decimals=18)},
        ),
    ]
)


def test_find_eth_transfers(description, transactions, tracks, expected_tracks):
    """
    Table-driven test for find_eth_transfers:
    - We pass various scenarios of transactions and tracks.
    - We verify which tracks got found
    """
    found_transfers = find_eth_transfers(transactions, tracks)
    found_tracks = set()
    for ft in found_transfers:
        found_tracks.add(ft.track)

    assert found_tracks == expected_tracks, f"{description} => track found mismatch"


# Example "event signature" for Transfer
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4..."

@pytest.mark.parametrize(
    "description, logs, tracks, expected_found_transfers",
    [
        (
            "Valid log with matching address and value",
            [
                {
                    "address": "0x1234567890abcdef",  # contract address
                    "topics": [TRANSFER_TOPIC],
                    "transactionHash": b"\x01\x02\x03",
                    "data": "0x00",
                }
            ],
            {
                Track(address="0xabcdef", amount=Decimal("10"), decimals=18, contract_address="0x1234567890abcdef"),
            },
            [
                FoundTransfer(track=Track(address="0xabcdef", amount=Decimal("10"), decimals=18, contract_address="0x1234567890abcdef"), tx_hash="010203")
            ]
        ),
        (
            "Log with different contract address",
            [
                {
                    "address": "0x9876543210fedcba",  # different contract address
                    "topics": [TRANSFER_TOPIC],
                    "transactionHash": b"\x01\x02\x03",
                    "data": "0x00",
                }
            ],
            {
                Track(address="0xabcdef", amount=Decimal("10"), decimals=18, contract_address="0x1234567890abcdef"),
            },
            []  # No matching transfers different contract address
        ),
        (
            "Log with matching address but value mismatch",
            [
                {
                    "address": "0x1234567890abcdef",  # matching contract address
                    "topics": [TRANSFER_TOPIC],
                    "transactionHash": b"\x01\x02\x03",
                    "data": "0x00",
                }
            ],
            {
                Track(address="0xabcdef", amount=Decimal("20"), decimals=18, contract_address="0x1234567890abcdef"),
            },
            []  # Amount mismatch, so no matches
        ),
        (
            "Log with matching address and value but wrong decimals",
            [
                {
                    "address": "0x1234567890abcdef",  # matching contract address
                    "topics": [TRANSFER_TOPIC],
                    "transactionHash": b"\x01\x02\x03",
                    "data": "0x00",
                }
            ],
            {
                Track(address="0xabcdef", amount=Decimal("10"), decimals=6, contract_address="0x1234567890abcdef"),
            },
            []  # Decimals mismatch, so no matches
        ),
    ]
)
def test_process_erc20_logs(description, logs, tracks, expected_found_transfers):
    """
    Table-driven test for process_erc20_logs:
    """
    # Setup TrackService with a mock logger and web3
    mock_logger = MagicMock()
    service = TrackService(repository=None, eth_rpc_url="", logger=mock_logger)
    service.web3 = MagicMock()

    # Mock the contract and `process_log` method
    mock_contract = MagicMock()
    mock_contract.functions.decimals.return_value = 18
    mock_transfer_event = MagicMock()
    mock_transfer_event.process_log.return_value = MagicMock(
        args={
            "from": "0xfromaddress",
            "to": "0xabcdef",  # Address matching the track
            "value": 10 * 10**18,  # 10 tokens with 18 decimals
        }
    )
    mock_contract.events.Transfer.return_value = mock_transfer_event
    service.web3.eth.contract.return_value = mock_contract

    found_transfers = service.process_erc20_logs(logs, tracks)

    assert found_transfers == expected_found_transfers, f"{description} failed"