"""
RPC routes
rpc version: 0.8.0
"""
from __future__ import annotations

import base64
import json
from typing import Callable, Union, List, Tuple, Optional, Any

from starkware.starknet.services.api.contract_class import ContractClass, EntryPointType
from typing_extensions import TypedDict

from flask import Blueprint, request

from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from starkware.starkware_utils.error_handling import StarkException
from starkware.starknet.services.api.feeder_gateway.response_objects import (
    StarknetBlock,
    InvokeSpecificInfo,
    DeploySpecificInfo,
    TransactionReceipt,
    TransactionStatus,
    TransactionSpecificInfo,
    TransactionType,
    BlockStateUpdate
)

from starknet_devnet.state import state
from ..util import StarknetDevnetException

rpc = Blueprint("rpc", __name__, url_prefix="/rpc")

PROTOCOL_VERSION = "0.8.0"

@rpc.route("", methods=["POST"])
async def base_route():
    """
    Base route for RPC calls
    """
    method, args, message_id = parse_body(request.json)

    try:
        result = await method(*args) if isinstance(args, list) else await method(**args)
    except NotImplementedError:
        return rpc_error(message_id=message_id, code=-2, message="Method not implemented")
    except RpcError as error:
        return rpc_error(message_id=message_id, code=error.code, message=error.message)

    return rpc_response(message_id=message_id, content=result)


async def get_block_by_hash(block_hash: str, requested_scope: str = "TXN_HASH") -> dict:
    """
    Get block information given the block id
    """
    try:
        result = state.starknet_wrapper.blocks.get_by_hash(block_hash=block_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=24, message="Invalid block hash") from ex

    return await rpc_block(block=result, requested_scope=requested_scope)


async def get_block_by_number(block_number: int, requested_scope: str = "TXN_HASH") -> dict:
    """
    Get block information given the block number (its height)
    """
    try:
        result = state.starknet_wrapper.blocks.get_by_number(block_number=block_number)
    except StarknetDevnetException as ex:
        raise RpcError(code=26, message="Invalid block number") from ex

    return await rpc_block(block=result, requested_scope=requested_scope)


async def get_state_update_by_hash(block_hash: str) -> dict:
    """
    Get the information about the result of executing the requested block
    """
    try:
        result = state.starknet_wrapper.blocks.get_state_update(block_hash=block_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=24, message="Invalid block hash") from ex

    return rpc_state_update(result)


async def get_storage_at(contract_address: str, key: str, block_hash: str) -> str:
    """
    Get the value of the storage at the given address and key
    """
    if block_hash != "latest":
        # By RPC here we should return `24 invalid block hash` but in this case I believe it's more
        # descriptive to the user to use a custom error
        raise RpcError(code=-1, message="Calls with block_hash != 'latest' are not supported currently.")

    if not state.starknet_wrapper.contracts.is_deployed(int(contract_address, 16)):
        raise RpcError(code=20, message="Contract not found")

    return await state.starknet_wrapper.get_storage_at(
        contract_address=int(contract_address, 16),
        key=int(key, 16)
    )


async def get_transaction_by_hash(transaction_hash: str) -> dict:
    """
    Get the details and status of a submitted transaction
    """
    try:
        result = state.starknet_wrapper.transactions.get_transaction(transaction_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=25, message="Invalid transaction hash") from ex

    if result.status == TransactionStatus.NOT_RECEIVED:
        raise RpcError(code=25, message="Invalid transaction hash")

    return rpc_transaction(result.transaction)


async def get_transaction_by_block_hash_and_index(block_hash: str, index: int) -> dict:
    """
    Get the details of a transaction by a given block hash and index
    """
    try:
        block = state.starknet_wrapper.blocks.get_by_hash(block_hash=block_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=24, message="Invalid block hash") from ex

    try:
        transaction_hash: int = block.transactions[index].transaction_hash
        return await get_transaction_by_hash(transaction_hash=rpc_felt(transaction_hash))
    except IndexError as ex:
        raise RpcError(code=27, message="Invalid transaction index in a block") from ex


async def get_transaction_by_block_number_and_index(block_number: int, index: int) -> dict:
    """
    Get the details of a transaction by a given block number and index
    """
    try:
        block = state.starknet_wrapper.blocks.get_by_number(block_number=block_number)
    except StarknetDevnetException as ex:
        raise RpcError(code=26, message="Invalid block number") from ex

    try:
        transaction_hash: int = block.transactions[index].transaction_hash
        return await get_transaction_by_hash(transaction_hash=rpc_felt(transaction_hash))
    except IndexError as ex:
        raise RpcError(code=27, message="Invalid transaction index in a block") from ex


async def get_transaction_receipt(transaction_hash: str) -> dict:
    """
    Get the transaction receipt by the transaction hash
    """
    try:
        result = state.starknet_wrapper.transactions.get_transaction_receipt(tx_hash=transaction_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=25, message="Invalid transaction hash") from ex

    if result.status == TransactionStatus.NOT_RECEIVED:
        raise RpcError(code=25, message="Invalid transaction hash")

    return rpc_transaction_receipt(result)


async def get_code(contract_address: str) -> dict:
    """
    Get the code of a specific contract
    """
    try:
        result = state.starknet_wrapper.contracts.get_code(address=int(contract_address, 16))
    except StarknetDevnetException as ex:
        raise RpcError(code=20, message="Contract not found") from ex

    if len(result["bytecode"]) == 0:
        raise RpcError(code=20, message="Contract not found")

    return {
        "bytecode": result["bytecode"],
        "abi": json.dumps(result["abi"])
    }


async def get_class(class_hash: str) -> dict:
    """
    Get the code of a specific contract
    """
    try:
        result = state.starknet_wrapper.contracts.get_class_by_hash(class_hash=int(class_hash, 16))
    except StarknetDevnetException as ex:
        raise RpcError(code=28, message="The supplied contract class hash is invalid or unknown") from ex

    return rpc_contract_class(result)


async def get_class_hash_at(contract_address: str) -> str:
    try:
        result = state.starknet_wrapper.contracts.get_class_hash_at(address=int(contract_address, 16))
    except StarknetDevnetException as ex:
        raise RpcError(code=28, message="The supplied contract class hash is invalid or unknown") from ex

    return rpc_felt(result)


async def get_class_at(contract_address: str) -> dict:
    try:
        class_hash = state.starknet_wrapper.contracts.get_class_hash_at(address=int(contract_address, 16))
        result = state.starknet_wrapper.contracts.get_class_by_hash(class_hash=class_hash)
    except StarknetDevnetException as ex:
        raise RpcError(code=20, message="Contract not found") from ex

    return rpc_contract_class(result)


async def get_block_transaction_count_by_hash(block_hash: str) -> int:
    """
    Get the number of transactions in a block given a block hash
    """
    try:
        block = state.starknet_wrapper.blocks.get_by_hash(block_hash=block_hash)
        return len(block.transactions)
    except StarknetDevnetException as ex:
        raise RpcError(code=24, message="Invalid block hash") from ex


async def get_block_transaction_count_by_number(block_number: int) -> int:
    """
    Get the number of transactions in a block given a block number (height)
    """
    try:
        block = state.starknet_wrapper.blocks.get_by_number(block_number=block_number)
        return len(block.transactions)
    except StarknetDevnetException as ex:
        raise RpcError(code=26, message="Invalid block number") from ex


async def call(contract_address: str, entry_point_selector: str, calldata: list, block_hash: str = "") -> list:
    """
    Call a starknet function without creating a StarkNet transaction
    """
    request_body = {
        "contract_address": contract_address,
        "entry_point_selector": entry_point_selector,
        "calldata": calldata
    }

    # For now, we only support 'latest' block, support for specific blocks
    # in devnet is more complicated if possible at all
    if block_hash != "latest":
        # By RPC here we should return `24 invalid block hash` but in this case I believe it's more
        # descriptive to the user to use a custom error
        raise RpcError(code=-1, message="Calls with block_hash != 'latest' are not supported currently.")

    if not state.starknet_wrapper.contracts.is_deployed(int(contract_address, 16)):
        raise RpcError(code=20, message="Contract not found")

    try:
        return await state.starknet_wrapper.call(transaction=make_invoke_function(request_body))
    except StarknetDevnetException as ex:
        raise RpcError(code=-1, message=ex.message) from ex
    except StarkException as ex:
        if f"Entry point {entry_point_selector} not found" in ex.message:
            raise RpcError(code=21, message="Invalid message selector") from ex
        if "While handling calldata" in ex.message:
            raise RpcError(code=22, message="Invalid call data") from ex
        raise RpcError(code=-1, message=ex.message) from ex


async def estimate_fee():
    pass


async def get_block_number() -> int:
    """
    Get the most recent accepted block number
    """
    result = state.starknet_wrapper.blocks.get_number_of_blocks() - 1
    return result if result >= 0 else 0


async def chain_id() -> str:
    """
    Return the currently configured StarkNet chain id
    """
    devnet_state = await state.starknet_wrapper.get_state()
    config = devnet_state.general_config
    chain: int = config.chain_id.value
    return hex(chain)


async def pending_transactions():
    """
    Returns the transactions in the transaction pool, recognized by this sequencer
    """
    raise NotImplementedError()


async def protocol_version() -> str:
    """
    Returns the current starknet protocol version identifier, as supported by this sequencer
    """
    protocol_hex = PROTOCOL_VERSION.encode("utf-8").hex()
    return "0x" + protocol_hex


async def syncing():
    """
    Returns an object about the sync status, or false if the node is not synching
    """
    raise NotImplementedError()


async def get_events():
    """
    Returns all events matching the given filter
    """
    raise NotImplementedError()


def make_invoke_function(request_body: dict) -> InvokeFunction:
    """
    Convert RPC request to internal InvokeFunction
    """
    return InvokeFunction(
        contract_address=int(request_body["contract_address"], 16),
        entry_point_selector=int(request_body["entry_point_selector"], 16),
        calldata=[int(data, 16) for data in request_body["calldata"]],
        max_fee=0,
        version=0,
        signature=[],
    )


class EntryPoint(TypedDict):
    offset: str
    selector: str


class EntryPoints(TypedDict):
    CONSTRUCTOR: List[EntryPoint]
    EXTERNAL: List[EntryPoint]
    L1_HANDLER: List[EntryPoint]


class RpcContractClass(TypedDict):
    program: str
    entry_point_by_type: EntryPoints


def rpc_contract_class(contract_class: ContractClass) -> RpcContractClass:
    """
    Convert gateway contract class to rpc contract class
    """
    def program() -> str:
        prog: str = contract_class.program.Schema().dumps(contract_class.program)
        prog_encoded = prog.encode("ascii")
        prog_base64 = base64.b64encode(prog_encoded)
        return prog_base64.decode()

    def entry_point_by_type() -> EntryPoints:
        _entry_points = {
            EntryPointType.CONSTRUCTOR: [],
            EntryPointType.EXTERNAL: [],
            EntryPointType.L1_HANDLER: [],
        }
        for typ, entry_points in contract_class.entry_points_by_type.items():
            for entry_point in entry_points:
                _entry_point: EntryPoint = {
                    "selector": rpc_felt(entry_point.selector),
                    "offset": rpc_felt(entry_point.offset)
                }
                _entry_points[typ].append(_entry_point)
        entry_points: EntryPoints = {
            "CONSTRUCTOR": _entry_points[EntryPointType.CONSTRUCTOR],
            "EXTERNAL": _entry_points[EntryPointType.EXTERNAL],
            "L1_HANDLER": _entry_points[EntryPointType.L1_HANDLER],
        }
        return entry_points

    _contract_class: RpcContractClass = {
        "program": program(),
        "entry_point_by_type": entry_point_by_type()
    }
    return _contract_class


class RpcBlock(TypedDict):
    """
    TypeDict for rpc block
    """
    block_hash: str
    parent_hash: str
    block_number: int
    status: str
    sequencer: str
    new_root: str
    old_root: str
    accepted_time: int
    transactions: List[str] | List[dict]


async def rpc_block(block: StarknetBlock, requested_scope: Optional[str] = "TXN_HASH") -> RpcBlock:
    """
    Convert gateway block to rpc block
    """
    async def transactions() -> List[RpcTransaction]:
        # pylint: disable=no-member
        return [rpc_transaction(tx) for tx in block.transactions]

    async def transaction_hashes() -> List[str]:
        return [tx["txn_hash"] for tx in await transactions()]

    async def full_transactions() -> list[dict[str, Any]]:
        transactions_and_receipts = []
        _transactions = await transactions()
        for transaction in _transactions:
            receipt = await get_transaction_receipt(transaction["txn_hash"])
            combined = {**receipt, **transaction}
            transactions_and_receipts.append(combined)
        return transactions_and_receipts

    def new_root() -> str:
        # pylint: disable=no-member
        return rpc_root(block.state_root.hex())

    def old_root() -> str:
        _root = state.starknet_wrapper.blocks.get_by_number(block_number=block_number - 1).state_root \
            if block_number - 1 >= 0 \
            else b"\x00" * 32
        return rpc_root(_root.hex())

    block_number = block.block_number

    mapping: dict[str, Callable] = {
        "TXN_HASH": transaction_hashes,
        "FULL_TXNS": transactions,
        "FULL_TXN_AND_RECEIPTS": full_transactions,
    }
    transactions: list = await mapping[requested_scope]()

    devnet_state = await state.starknet_wrapper.get_state()
    config = devnet_state.general_config

    block: RpcBlock = {
        "block_hash": rpc_felt(block.block_hash),
        "parent_hash": rpc_felt(block.parent_block_hash) or "0x0",
        "block_number": block.block_number if block.block_number is not None else 0,
        "status": block.status.name,
        "sequencer": hex(config.sequencer_address),
        "new_root": new_root(),
        "old_root": old_root(),
        "accepted_time": block.timestamp,
        "transactions": transactions,
    }
    return block


class RpcStorageDiff(TypedDict):
    """
    TypedDict for rpc storage diff
    """
    address: str
    key: str
    value: str


class RpcContractDiff(TypedDict):
    """
    TypedDict for rpc contract diff
    """
    address: str
    contract_hash: str


class RpcStateDiff(TypedDict):
    """
    TypedDict for roc state diff
    """
    storage_diffs: List[RpcStorageDiff]
    contracts: List[RpcContractDiff]


class RpcStateUpdate(TypedDict):
    """
    TypedDict for rpc state update
    """
    block_hash: str
    new_root: str
    old_root: str
    accepted_time: int
    state_diff: RpcStateDiff


def rpc_state_update(state_update: BlockStateUpdate) -> RpcStateUpdate:
    """
    Convert gateway state update to rpc state update
    """
    def storage_diffs() -> List[RpcStorageDiff]:
        _storage_diffs = []
        for address, diffs in state_update.state_diff.storage_diffs.items():
            for diff in diffs:
                _diff: RpcStorageDiff = {
                    "address": rpc_felt(address),
                    "key": rpc_felt(diff.key),
                    "value": rpc_felt(diff.value),
                }
                _storage_diffs.append(_diff)
        return _storage_diffs

    def contracts() -> List[RpcContractDiff]:
        _contracts = []
        for contract in state_update.state_diff.deployed_contracts:
            diff: RpcContractDiff = {
                "address": rpc_felt(contract.address),
                "contract_hash": rpc_root(contract.class_hash.hex())
            }
            _contracts.append(diff)
        return _contracts

    def timestamp() -> int:
        block = state.starknet_wrapper.blocks.get_by_hash(block_hash=hex(state_update.block_hash))
        return block.timestamp

    rpc_state: RpcStateUpdate = {
        "block_hash": rpc_felt(state_update.block_hash),
        "new_root": rpc_root(state_update.new_root.hex()),
        "old_root": rpc_root(state_update.old_root.hex()),
        "accepted_time": timestamp(),
        "state_diff": {
            "storage_diffs": storage_diffs(),
            "contracts": contracts(),
        }
    }
    return rpc_state


def rpc_state_diff_contract(contract: dict) -> dict:
    """
    Convert gateway contract state diff to rpc contract state diff
    """
    return {
        "address": contract["address"],
        "contract_hash": f"0x{contract['contract_hash']}",
    }


def rpc_state_diff_storage(contract: dict) -> dict:
    """
    Convert gateway storage state diff to rpc storage state diff
    """
    return {
        "address": contract["address"],
        "key": contract["key"],
        "value": contract["value"],
    }


class RpcTransaction(TypedDict):
    """
    TypedDict for rpc transaction
    """
    contract_address: str
    entry_point_selector: Optional[str]
    calldata: Optional[List[str]]
    max_fee: str
    txn_hash: str


def rpc_invoke_transaction(transaction: InvokeSpecificInfo) -> RpcTransaction:
    """
    Convert gateway invoke transaction to rpc format
    """
    transaction: RpcTransaction = {
        "contract_address": rpc_felt(transaction.contract_address),
        "entry_point_selector": rpc_felt(transaction.entry_point_selector),
        "calldata": [rpc_felt(data) for data in transaction.calldata],
        "max_fee": rpc_felt(transaction.max_fee),
        "txn_hash": rpc_felt(transaction.transaction_hash),
    }
    return transaction


def rpc_deploy_transaction(transaction: DeploySpecificInfo) -> RpcTransaction:
    """
    Convert gateway deploy transaction to rpc format
    """
    def calldata() -> Optional[List[str]]:
        # pylint: disable=no-member
        _calldata = transaction.constructor_calldata
        if not _calldata:
            return None
        return [rpc_felt(data) for data in _calldata]

    transaction: RpcTransaction = {
        "contract_address": rpc_felt(transaction.contract_address),
        "entry_point_selector": None,
        "calldata": calldata(),
        "max_fee": rpc_felt(0),
        "txn_hash": rpc_felt(transaction.transaction_hash),
    }
    return transaction


def rpc_transaction(transaction: TransactionSpecificInfo) -> RpcTransaction:
    """
    Convert gateway transaction to rpc transaction
    """
    tx_mapping = {
        TransactionType.DEPLOY: rpc_deploy_transaction,
        TransactionType.INVOKE_FUNCTION: rpc_invoke_transaction
    }
    return tx_mapping[transaction.tx_type](transaction)


class MessageToL1(TypedDict):
    """
    TypedDict for rpc message from l2 to l1
    """
    to_address: str
    payload: List[str]


class MessageToL2(TypedDict):
    """
    TypedDict for rpc message from l1 to l2
    """
    from_address: str
    payload: List[str]


class Event(TypedDict):
    """
    TypedDict for rpc event
    """
    from_address: str
    keys: List[str]
    data: List[str]


class RpcReceipt(TypedDict):
    """
    TypedDict for rpc transaction receipt
    """
    txn_hash: str
    actual_fee: str
    status: str
    statusData: str
    messages_sent: List[MessageToL1]
    l1_origin_message: Optional[MessageToL2]
    events: List[Event]


def rpc_transaction_receipt(txr: TransactionReceipt) -> RpcReceipt:
    """
    Convert gateway transaction receipt to rpc transaction receipt
    """
    def l2_to_l1_messages() -> List[MessageToL1]:
        messages = []
        for message in txr.l2_to_l1_messages:
            msg: MessageToL1 = {
                "to_address": message.to_address,
                "payload": [rpc_felt(p) for p in message.payload]
            }
            messages.append(msg)
        return messages

    def l1_to_l2_message() -> Optional[MessageToL2]:
        if txr.l1_to_l2_consumed_message is None:
            return None

        msg: MessageToL2 = {
            "from_address": txr.l1_to_l2_consumed_message.from_address,
            "payload": [rpc_felt(p) for p in txr.l1_to_l2_consumed_message.payload]
        }
        return msg

    def events() -> List[Event]:
        _events = []
        for event in txr.events:
            event: Event = {
                "from_address": rpc_felt(event.from_address),
                "keys": [rpc_felt(e) for e in event.keys],
                "data": [rpc_felt(d) for d in event.data],
            }
            _events.append(event)
        return _events

    def status() -> str:
        if txr.status is None:
            return "UNKNOWN"

        mapping = {
            TransactionStatus.NOT_RECEIVED: "UNKNOWN",
            TransactionStatus.ACCEPTED_ON_L2: "ACCEPTED_ON_L2",
            TransactionStatus.ACCEPTED_ON_L1: "ACCEPTED_ON_L1",
            TransactionStatus.RECEIVED: "RECEIVED",
            TransactionStatus.PENDING: "PENDING",
            TransactionStatus.REJECTED: "REJECTED",
        }
        return mapping[txr.status]

    receipt: RpcReceipt = {
        "txn_hash": rpc_felt(txr.transaction_hash),
        "status": status(),
        "statusData": "",
        "messages_sent": l2_to_l1_messages(),
        "l1_origin_message": l1_to_l2_message(),
        "events": events(),
        "actual_fee": rpc_felt(txr.actual_fee or 0),
    }
    return receipt


def rpc_response(message_id: int, content: dict) -> dict:
    """
    Wrap response content in rpc format
    """
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": content
    }


def rpc_error(message_id: int, code: int, message: str) -> dict:
    """
    Wrap error in rpc format
    """
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message
        }
    }


def rpc_felt(value: int) -> str:
    """
    Convert integer to 0x0 prefixed felt
    """
    return "0x0" + hex(value).lstrip("0x")


def rpc_root(root: str) -> str:
    """
    Convert 0 prefixed root to 0x prefixed root
    """
    root = root[1:]
    return "0x0" + root


def parse_body(body: dict) -> Tuple[Callable, Union[List, dict], int]:
    """
    Parse rpc call body to function name and params
    """
    methods = {
        "getBlockByNumber": get_block_by_number,
        "getBlockByHash": get_block_by_hash,
        "getStateUpdateByHash": get_state_update_by_hash,
        "getStorageAt": get_storage_at,
        "getTransactionByHash": get_transaction_by_hash,
        "getTransactionByBlockHashAndIndex": get_transaction_by_block_hash_and_index,
        "getTransactionByBlockNumberAndIndex": get_transaction_by_block_number_and_index,
        "getTransactionReceipt": get_transaction_receipt,
        "getCode": get_code,
        "getBlockTransactionCountByHash": get_block_transaction_count_by_hash,
        "getBlockTransactionCountByNumber": get_block_transaction_count_by_number,
        "call": call,
        "blockNumber": get_block_number,
        "chainId": chain_id,
        "pendingTransactions": pending_transactions,
        "protocolVersion": protocol_version,
        "syncing": syncing,
        "getEvents": get_events,
        "getClass": get_class,
        "getClassHashAt": get_class_hash_at,
        "getClassAt": get_class_at,
        "estimateFee": estimate_fee,
    }

    method_name = body["method"].lstrip("starknet_")
    args: Union[List, dict] = body["params"]
    message_id = body["id"]

    if method_name not in methods:
        raise RpcError(code=-1, message="Method not found")

    return methods[method_name], args, message_id


class RpcError(Exception):
    """
    Error message returned by rpc
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
