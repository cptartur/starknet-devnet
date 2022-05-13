"""
RPC routes
"""
# TODO change formatting to be uniform with rest of devnet
import json

from flask import Blueprint, request
from typing import Callable, Union, List, Tuple

from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from starkware.starkware_utils.error_handling import StarkException

from starknet_devnet.state import state
from ..util import StarknetDevnetException

rpc = Blueprint("rpc", __name__, url_prefix="/rpc")


@rpc.route("", methods=["POST"])
async def base_route():
    method, args, message_id = parse_body(request.json)

    try:
        result = await method(*args) if isinstance(args, list) else await method(**args)
    except TypeError as error:
        return rpc_error(message_id=message_id, code=-1, message=str(error))
    except RpcError as error:
        return rpc_error(message_id=message_id, code=error.code, message=error.message)

    return rpc_response(message_id=message_id, content=result)


async def get_block_by_hash(block_hash: str, requested_scope: str = "TXN_HASH") -> dict:
    try:
        result = state.starknet_wrapper.get_block_by_hash(block_hash=block_hash)
    except StarknetDevnetException:
        raise RpcError(code=24, message="Invalid block hash")

    return rpc_block(block=result, requested_scope=requested_scope)


async def get_block_by_number(block_number: int, requested_scope: str = "TXN_HASH") -> dict:
    try:
        result = state.starknet_wrapper.get_block_by_number(block_number=block_number)
    except StarknetDevnetException:
        raise RpcError(code=26, message="Invalid block number")

    return rpc_block(block=result, requested_scope=requested_scope)


async def get_state_update_by_hash(block_hash: str) -> dict:
    try:
        result = state.starknet_wrapper.get_state_update(block_hash=block_hash)
    except StarknetDevnetException:
        raise RpcError(code=24, message="Invalid block hash")

    return rpc_state_update(result)


async def get_storage_at(contract_address: str, key: str, block_hash: str) -> str:
    # TODO improve logic
    block = state.starknet_wrapper.get_block_by_hash(block_hash=block_hash)
    if block is None:
        raise RpcError(code=24, message="Invalid block hash")

    return await state.starknet_wrapper.get_storage_at(
        contract_address=int(contract_address, 16),
        key=int(key, 16)
    )


async def get_transaction_by_hash(transaction_hash) -> dict:
    # TODO improve logic
    result = state.starknet_wrapper.get_transaction(transaction_hash)

    if "transaction" not in result:
        raise RpcError(25, "Invalid transaction hash")

    tx = result["transaction"]
    return rpc_transaction(tx)


async def get_transaction_by_block_hash_and_index(block_hash: str, index: int) -> dict:
    try:
        block = state.starknet_wrapper.get_block_by_hash(block_hash=block_hash)
    except StarknetDevnetException:
        raise RpcError(code=24, message="Invalid block hash")

    try:
        transaction_hash = block["transactions"][index]["transaction_hash"]
        return await get_transaction_by_hash(transaction_hash=transaction_hash)
    except IndexError:
        raise RpcError(code=27, message="Invalid transaction index in a block")


async def get_transaction_by_block_number_and_index(block_number: int, index: int) -> dict:
    try:
        block = state.starknet_wrapper.get_block_by_number(block_number=block_number)
    except StarknetDevnetException:
        raise RpcError(code=26, message="Invalid block number")

    try:
        transaction_hash = block["transactions"][index]["transaction_hash"]
        return await get_transaction_by_hash(transaction_hash=transaction_hash)
    except IndexError:
        raise RpcError(code=27, message="Invalid transaction index in a block")


async def get_transaction_receipt(transaction_hash: str) -> dict:
    try:
        result = state.starknet_wrapper.get_transaction_receipt(transaction_hash=transaction_hash)
        return rpc_transaction_receipt(result)
    except StarknetDevnetException:
        raise RpcError(code=25, message="Invalid transaction hash")


async def get_code(contract_address: str) -> dict:
    try:
        result = state.starknet_wrapper.get_code(contract_address=int(contract_address, 16))
    except StarknetDevnetException:
        raise RpcError(code=20, message="Contract not found")

    return {
        "bytecode": result["bytecode"],
        "abi": json.dumps(result["abi"])
    }


async def get_block_transaction_count_by_hash(block_hash: str) -> int:
    try:
        block = state.starknet_wrapper.get_block_by_hash(block_hash=block_hash)
        return len(block["transactions"])
    except StarknetDevnetException:
        raise RpcError(code=24, message="Invalid block hash")


async def get_block_transaction_count_by_number(block_number: int) -> int:
    try:
        block = state.starknet_wrapper.get_block_by_number(block_number=block_number)
        return len(block["transactions"])
    except StarknetDevnetException:
        raise RpcError(code=26, message="Invalid block number")


async def call(contract_address: str, entry_point_selector: str, calldata: list, block_hash: str = "") -> list:
    request_body = {
        "contract_address": contract_address,
        "entry_point_selector": entry_point_selector,
        "calldata": calldata
    }

    # For now, we only support 'latest' block, support for specific blocks
    # in devnet is more complicated if possible at all
    if block_hash != "latest":
        raise RpcError(code=-1, message="Calls with block_hash != 'latest' are not supported currently.")

    try:
        return await state.starknet_wrapper.call(transaction=make_invoke_function(request_body))
    except StarknetDevnetException as ex:
        if f"No contract at the provided address" in ex.message:
            raise RpcError(code=20, message="Contract not found")
        raise RpcError(code=-1, message=ex.message)
    except StarkException as ex:
        if f"Entry point {entry_point_selector} not found" in ex.message:
            raise RpcError(code=21, message="Invalid message selector")
        if f"While handling calldata" in ex.message:
            raise RpcError(code=22, message="Invalid call data")
        raise RpcError(code=-1, message=ex.message)


async def get_block_number() -> int:
    result = state.starknet_wrapper.get_number_of_blocks() - 1
    return result if result >= 0 else 0


def make_invoke_function(request_body: dict) -> InvokeFunction:
    return InvokeFunction(
        contract_address=int(request_body["contract_address"], 16),
        entry_point_selector=int(request_body["entry_point_selector"], 16),
        calldata=[int(data, 16) for data in request_body["calldata"]],
        max_fee=0,
        version=0,
        signature=[],
    )


def rpc_block(block: dict, requested_scope: str) -> dict:
    block_number = block["block_number"]
    old_root = state.starknet_wrapper.get_block_by_number(
        block_number=block_number - 1) if block_number - 1 >= 0 else "0x0"

    transactions = []
    if requested_scope == "TXN_HASH":
        transactions = [tx["transaction_hash"] for tx in block["transactions"]]
    elif requested_scope == "FULL_TXNS":
        transactions = [rpc_transaction(tx) for tx in block["transactions"]]
    elif requested_scope == "FULL_TXN_AND_RECEIPTS":
        tx = [rpc_transaction(tx) for tx in block["transactions"]]
        receipts = [
            rpc_transaction_receipt(state.starknet_wrapper.get_transaction_receipt(tx["transaction_hash"]))
            for tx
            in block["transactions"]
        ]
        transactions = [{**transaction, **receipt} for transaction, receipt in zip(tx, receipts)]

    return {
        "block_hash": block["block_hash"],
        "parent_hash": block["parent_block_hash"] or "0x0",
        "block_number": block["block_number"],
        "status": block["status"],
        "sequencer": "0x0000000000000000000000000000000000000000",
        "new_root": block["state_root"],
        "old_root": old_root,
        "accepted_time": block["timestamp"],
        "transactions": transactions,
    }


def rpc_state_update(state_update: dict) -> dict:
    return {
        "block_hash": state_update["block_hash"],
        "new_root": state_update["new_root"],
        "old_root": state_update["old_root"],
        "accepted_time": 0,  # hardcoded value as state_update dict does not contain timestamp
        "state_diff": {
            "deployed_contracts": [
                rpc_state_diff_contract(contract)
                for contract
                in state_update["state_diff"]["deployed_contracts"]
            ],
            "storage_diffs": [
                {
                    **{
                        "address": address
                    },
                    **storage
                }
                for address, storage
                in state_update["state_diff"]["storage_diffs"].items()
            ],
        },
    }


def rpc_state_diff_contract(contract: dict) -> dict:
    return {
        "address": contract["address"],
        "contract_hash": f"0x{contract['contract_hash']}",
    }


def rpc_state_diff_storage(contract: dict) -> dict:
    return {
        "address": contract["address"],
        "key": contract["key"],
        "value": contract["value"],
    }


def rpc_transaction(tx: dict) -> dict:
    return {
        "txn_hash": tx.get("transaction_hash"),
        "contract_address": tx.get("contract_address"),
        "entry_point_selector": tx.get("entry_point_selector"),
        "calldata": tx.get("calldata"),
    }


def rpc_transaction_receipt(txr: dict) -> dict:
    return {
        "txn_hash": txr["transaction_hash"],
        "status": txr["status"],
        "statusData": "",
        "messages_sent": txr["l2_to_l1_messages"] or [],
        "l1_origin_message": None,
        "events": txr["events"] or [],
    }


def rpc_response(message_id: int, content: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": content
    }


def rpc_error(message_id: int, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message
        }
    }


def parse_body(body: dict) -> Tuple[Callable, Union[List, dict], int]:
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
    }

    method_name = body["method"].lstrip("starknet_")
    args: Union[List, dict] = body["params"]
    message_id = body["id"]

    if method_name not in methods:
        raise RpcError(code=-1, message="Method not found")

    return methods[method_name], args, message_id


class RpcError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
