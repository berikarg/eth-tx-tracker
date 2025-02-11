# import logging
# import pytest
# from decimal import Decimal
# from unittest.mock import Mock, MagicMock
#
# from src.service.track_service import TrackService
# from src.models.track import Track
# from src.repository.track_repository import TrackRepository
#
# logger = logging.getLogger(__name__)
#
# def test_find_eth_transfers():
#     """
#     Tests that _find_eth_transfers sets track.is_found = True
#     when a matching transaction is found.
#     """
#     repo = TrackRepository()
#     service = TrackService(repo, "", logger)
#
#     track = Track(address="0xabc", amount=Decimal("0.5"))
#     repo.add_track(track)
#
#     tx_data = {
#         "to": "0xAbC",
#         "value": int(0.5 * 10**18),
#         "hash": b"\x11\x22",
#     }
#
#     service._find_eth_transfers([tx_data], repo.list_tracks(), block_number=123)
#
#     assert track.is_found, "Track should be marked as found after matching ETH transfer."
#
# def test_find_erc20_transfers():
#     """
#     Tests that _find_erc20_transfers sets track.is_found = True
#     when a matching ERC-20 Transfer log is found.
#     """
#     repo = TrackRepository()
#     service = TrackService(repo, "", logger)
#
#     # A track expecting 100 tokens from contract 0xErc20
#     track = Track(address="0xabc", amount=Decimal("100"), contract_address="0xErc20")
#     repo.add_track(track)
#
#     # We'll mock web3 contract calls
#     mock_contract = MagicMock()
#     # decimals returns 2 for example
#     mock_contract.functions.decimals().call = Mock(return_value=2)
#     # We'll patch service.web3.eth.contract to return our mock_contract
#     service.web3.eth.contract = MagicMock(return_value=mock_contract)
#
#     # Create a fake log matching the contract address
#     fake_log = {
#         "address": "0xERC20",  # same as track.contract_address (ignoring case)
#         "topics": [],
#         "data": "",
#     }
#     # We also need the event object that parseLog would return
#     parsed_event_mock = MagicMock()
#     parsed_event_mock.args = {
#         "from": "0x123",
#         "to": "0xAbC",  # matches track.address
#         "value": 10000  # 100.00 with 2 decimals
#     }
#     # So that contract.events.Transfer().processLog(fake_log) returns parsed_event_mock
#     mock_contract.events.Transfer().processLog.return_value = parsed_event_mock
#
#     # Act
#     service._find_erc20_transfers([fake_log], repo.list_tracks(), 123, "0x11")
#
#     # Assert
#     assert track.is_found, "Track should be marked as found when a matching ERC-20 Transfer is logged."


import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.models.track import Track
from src.service.track_service import TrackService


@pytest.mark.parametrize(
    "description,transactions,tracks,expected_found",
    [
        (
            "No transactions => no track found",
            [],
            [Track(address="0xabc", amount=Decimal("1.0"))],
            [False],
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
            [Track(address="0xabc", amount=Decimal("1.0"))],
            [False],
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
            [Track(address="0xabc", amount=Decimal("1.0"))],
            [False],
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
            [Track(address="0xabc", amount=Decimal("1.0"))],
            [False],
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
            [Track(address="0xAbC", amount=Decimal("1.0"))],
            [True],
        ),
        (
            "Two transactions, second matches => only second track found",
            [
                {"to": "0x111", "value": 10**18, "hash": b"\x05"},  # mismatch
                {"to": "0xabc", "value": int(3 * 10**18), "hash": b"\x06"},  # match
            ],
            [Track(address="0xabc", amount=Decimal("3.0"))],
            [True],
        ),
        (
                "Two transactions, both match",
                [
                    {"to": "0x111", "value": 10 ** 18, "hash": b"\x05"},  # mismatch
                    {"to": "0xabc", "value": int(3 * 10 ** 18), "hash": b"\x06"},  # match
                ],
                [Track(address="0xabc", amount=Decimal("3.0")), Track(address="0x111", amount=Decimal("1.0"))],
                [True, True],
        ),
    ]
)

def test_find_eth_transfers(description, transactions, tracks, expected_found):
    """
    Table-driven test for _find_eth_transfers:
    - We pass various scenarios of transactions and tracks.
    - We verify which tracks got marked as found.
    """
    mock_logger = MagicMock()
    service = TrackService(repository=None, eth_rpc_url="", logger=mock_logger)
    for t in tracks:
        t.is_found = False

    service._find_eth_transfers(transactions, tracks, block_number=123)

    for track, exp in zip(tracks, expected_found):
        assert track.is_found == exp, f"{description} => track found mismatch"


# Example "event signature" for Transfer
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4..."

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "description,log_entries,tracks,expected_found",
    [
        (
            "No logs => no found tracks",
            [],
            [Track(address="0xAbC", amount=Decimal("100"), contract_address="0xToken")],
            [False],
        ),
        (
            "Log from different address => no match",
            [
                {
                    "address": "0xAnotherToken",
                    "topics": [TRANSFER_TOPIC],
                    "data": "",  # minimal
                }
            ],
            [Track(address="0xabc", amount=Decimal("100"), contract_address="0xToken")],
            [False],
        ),
        (
            "Log from same address, but decimal conversion doesn't match => not found",
            [
                {
                    "address": "0xToKeN",  # case difference
                    "topics": [TRANSFER_TOPIC],
                    "data": "",
                }
            ],
            [Track(address="0xabc", amount=Decimal("100"), contract_address="0xTOKEN")],
            [False],
        ),
        (
            "Log matches address and decimals => track found",
            [
                {
                    "address": "0xtoken",
                    "topics": [TRANSFER_TOPIC],
                    "data": "",  # real logs typically have data or topics for "from", "to", etc.
                }
            ],
            [Track(address="0xaBc", amount=Decimal("100.0"), contract_address="0xToKeN")],
            [True],
        ),
    ]
)
async def test_process_erc20_logs(description, log_entries, tracks, expected_found):
    """
    Table-driven test for _process_erc20_logs. We simulate get_logs returning
    some log entries, then verify tracks get updated if address/amount matches.
    """
    mock_logger = MagicMock()

    # We must mock the web3.eth.get_logs return value
    service = TrackService(repository=None, eth_rpc_url="", logger=mock_logger)
    mock_web3 = MagicMock()
    mock_web3.eth.get_logs = AsyncMock(return_value=log_entries)
    service.web3 = mock_web3  # replace real web3 with our mock

    # We'll also mock the contract and decimals call
    mock_contract = MagicMock()
    mock_contract.functions.decimals().call = AsyncMock(return_value=18)
    # For the event parser, let's mock .events.Transfer().process_log(...)
    mock_transfer_event = MagicMock()
    mock_transfer_event.process_log.return_value = MagicMock(
        args={
            "from": "0xFrom",
            "to": "0xaBc",  # matches track address
            "value": 100 * 10**18,  # 100.0 tokens at 18 decimals
        }
    )
    mock_contract.events.Transfer.return_value = mock_transfer_event
    mock_web3.eth.contract.return_value = mock_contract

    # Ensure tracks are initially not found
    for t in tracks:
        t.is_found = False

    # 2) Call the method
    block_num = 123456
    addresses = list({t.contract_address for t in tracks if t.contract_address})
    await service._process_erc20_logs(block_num, addresses, tracks)

    # 3) Check the results
    for track, exp in zip(tracks, expected_found):
        assert track.is_found == exp, f"{description} => expected {exp} but got {track.is_found}"