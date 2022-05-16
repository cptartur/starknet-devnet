"""
Tests RPC endpoints.
"""
from __future__ import annotations

import json

import pytest
from starkware.starknet.public.abi import get_storage_var_address, get_selector_from_name

from .util import (
    devnet_in_background,
    load_file_content,
)
from .test_endpoints import send_transaction

from starknet_devnet.server import app


DEPLOY_CONTENT = load_file_content("deploy.json")
INVOKE_CONTENT = load_file_content("invoke.json")


def rpc_call(method: str, params: dict | list) -> dict:
    req = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 0
    }

    resp = app.test_client().post(
        "/rpc",
        content_type="application/json",
        data=json.dumps(req)
    )
    result = json.loads(resp.data.decode("utf-8"))
    return result


def call_test_client(method: str, **kwargs):
    resp = app.test_client().get(
        f"/feeder_gateway/{method}?{''.join(f'{key}={value}&' for key, value in kwargs.items()).rstrip('&')}"
    )
    return json.loads(resp.data.decode("utf-8"))


def deploy_balance_contract() -> dict:
    resp = send_transaction(json.loads(DEPLOY_CONTENT))
    deploy_info = json.loads(resp.data.decode("utf-8"))
    return deploy_info


def deploy_invoke_contract() -> dict:
    invoke_tx = json.loads(INVOKE_CONTENT)
    invoke_tx["calldata"] = ["0"]
    resp = send_transaction(invoke_tx)
    deploy_info = json.loads(resp.data.decode("utf-8"))
    return deploy_info


def pad_zero(felt: str) -> str:
    felt = felt.lstrip("0x")
    return "0x0" + felt


def test_get_block_by_number():
    send_transaction(json.loads(DEPLOY_CONTENT))
    resp = rpc_call(
        "starknet_getBlockByNumber", params={"block_number": 0}
    )
    block = resp["result"]
    expected = {
        "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "block_number": 0,
        "status": "ACCEPTED_ON_L2",
        "sequencer": "0x0000000000000000000000000000000000000000",
        "old_root": "0x0",
    }

    for key, value in expected.items():
        assert block[key] == value


def test_get_block_by_number_raises_on_incorrect_number():
    ex = rpc_call(
        "starknet_getBlockByNumber", params={"block_number": 1234}
    )

    assert ex["error"] == {
        "code": 26,
        "message": "Invalid block number"
    }


def test_get_block_by_hash():
    send_transaction(json.loads(DEPLOY_CONTENT))
    resp1 = rpc_call(
        "starknet_getBlockByNumber", params={"block_number": 0}
    )
    block1 = resp1["result"]
    block_hash = block1["block_hash"]

    resp2 = rpc_call(
        "starknet_getBlockByHash", params={"block_hash": block_hash}
    )
    block2 = resp2["result"]
    expected = {
        "block_hash": block_hash,
        "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "block_number": 0,
        "status": "ACCEPTED_ON_L2",
        "sequencer": "0x0000000000000000000000000000000000000000",
        "old_root": "0x0",
    }

    for key, value in expected.items():
        assert block2[key] == value


def test_get_block_by_hash_raises_on_incorrect_hash():
    ex = rpc_call(
        "starknet_getBlockByHash", params={"block_hash": "0x0"}
    )

    assert ex["error"] == {
        "code": 24,
        "message": "Invalid block hash"
    }


def test_get_storage_at():
    resp = send_transaction(json.loads(DEPLOY_CONTENT))
    deploy_info = json.loads(resp.data.decode("utf-8"))
    block = call_test_client("get_block", blockNumber=0)

    contract_address: str = deploy_info["address"]
    key: str = str(hex(get_storage_var_address("balance")))
    block_hash: str = block["block_hash"]

    resp = rpc_call(
        "starknet_getStorageAt", params={
            "contract_address": contract_address,
            "key": key,
            "block_hash": block_hash,
        }
    )
    storage = resp["result"]

    assert storage == "0x0"


def test_get_storage_at_raises_on_incorrect_contract():
    resp = send_transaction(json.loads(DEPLOY_CONTENT))
    deploy_info = json.loads(resp.data.decode("utf-8"))
    block = call_test_client("get_block", blockNumber=0)

    key: str = str(hex(get_storage_var_address("balance")))
    block_hash: str = block["block_hash"]

    ex = rpc_call(
        "starknet_getStorageAt", params={
            "contract_address": "0x0",
            "key": key,
            "block_hash": block_hash,
        }
    )

    assert ex["error"] == {
        "code": 20,
        "message": "Contract not found"
    }


# FIXME internal workings of get_storage_at would have to be changed for this to work
#       since currently it will (correctly) return 0x0 for any incorrect key
@pytest.mark.xfail
def test_get_storage_at_raises_on_incorrect_key():
    resp = send_transaction(json.loads(DEPLOY_CONTENT))
    deploy_info = json.loads(resp.data.decode("utf-8"))
    block = call_test_client("get_block", blockNumber=0)

    contract_address: str = deploy_info["address"]
    key: str = str(hex(get_storage_var_address("balance")))
    block_hash: str = block["block_hash"]

    ex = rpc_call(
        "starknet_getStorageAt", params={
            "contract_address": contract_address,
            "key": "0x0",
            "block_hash": block_hash,
        }
    )

    assert ex["error"] == {
        "code": 23,
        "message": "Invalid storage key"
    }


def test_get_storage_at_raises_on_incorrect_block_hash():
    resp = send_transaction(json.loads(DEPLOY_CONTENT))
    deploy_info = json.loads(resp.data.decode("utf-8"))
    block = call_test_client("get_block", blockNumber=0)

    contract_address: str = deploy_info["address"]
    key: str = str(hex(get_storage_var_address("balance")))
    block_hash: str = block["block_hash"]

    ex = rpc_call(
        "starknet_getStorageAt", params={
            "contract_address": contract_address,
            "key": key,
            "block_hash": "0x0",
        }
    )

    assert ex["error"] == {
        "code": 24,
        "message": "Invalid block hash"
    }


def test_get_transaction_by_hash_deploy():
    deploy_info = deploy_balance_contract()
    transaction_hash: str = deploy_info["transaction_hash"]
    contract_address: str = deploy_info["address"]

    resp = rpc_call(
        "starknet_getTransactionByHash", params={"transaction_hash": transaction_hash}
    )
    transaction = resp["result"]

    assert transaction == {
        "txn_hash": pad_zero(transaction_hash),
        "contract_address": contract_address,
        "entry_point_selector": None,
        "calldata": None,
        "max_fee": "0x0"
    }


def test_get_transaction_by_hash_raises_on_incorrect_hash():
    ex = rpc_call(
        "starknet_getTransactionByHash", params={"transaction_hash": "0x0"}
    )

    assert ex["error"] == {
        "code": 25,
        "message": "Invalid transaction hash"
    }


def test_get_transaction_by_block_hash_and_index():
    deploy_info = deploy_balance_contract()
    block = call_test_client("get_block", blockNumber=0)
    transaction_hash: str = deploy_info["transaction_hash"]
    contract_address: str = deploy_info["address"]
    block_hash: str = block["block_hash"]
    index: int = 0

    resp = rpc_call(
        "starknet_getTransactionByBlockHashAndIndex", params={
            "block_hash": block_hash,
            "index": index
        }
    )
    transaction = resp["result"]

    assert transaction == {
        "txn_hash": pad_zero(transaction_hash),
        "contract_address": contract_address,
        "entry_point_selector": None,
        "calldata": None,
        "max_fee": "0x0",
    }


def test_get_transaction_by_block_hash_and_index_raises_on_incorrect_block_hash():
    ex = rpc_call(
        "starknet_getTransactionByBlockHashAndIndex", params={
            "block_hash": "0x0",
            "index": 0
        }
    )

    assert ex["error"] == {
        "code": 24,
        "message": "Invalid block hash"
    }


def test_get_transaction_by_block_hash_and_index_raises_on_incorrect_index():
    deploy_info = deploy_balance_contract()
    block = call_test_client("get_block", blockNumber=0)
    transaction_hash: str = deploy_info["transaction_hash"]
    contract_address: str = deploy_info["address"]
    block_hash: str = block["block_hash"]

    ex = rpc_call(
        "starknet_getTransactionByBlockHashAndIndex", params={
            "block_hash": block_hash,
            "index": 999999
        }
    )

    assert ex["error"] == {
        "code": 27,
        "message": "Invalid transaction index in a block"
    }


def test_get_transaction_by_block_number_and_index():
    deploy_info = deploy_balance_contract()
    transaction_hash: str = deploy_info["transaction_hash"]
    contract_address: str = deploy_info["address"]
    block_number: int = 0
    index: int = 0

    resp = rpc_call(
        "starknet_getTransactionByBlockNumberAndIndex", params={
            "block_number": block_number,
            "index": index
        }
    )
    transaction = resp["result"]

    assert transaction == {
        "txn_hash": pad_zero(transaction_hash),
        "contract_address": contract_address,
        "entry_point_selector": None,
        "calldata": None,
        "max_fee": "0x0",
    }


def test_get_transaction_by_block_number_and_index_raises_on_incorrect_block_number():
    ex = rpc_call(
        "starknet_getTransactionByBlockNumberAndIndex", params={
            "block_number": 99999,
            "index": 0
        }
    )

    assert ex["error"] == {
        "code": 26,
        "message": "Invalid block number"
    }


def test_get_transaction_by_block_number_and_index_raises_on_incorrect_index():
    deploy_info = deploy_balance_contract()
    transaction_hash: str = deploy_info["transaction_hash"]
    contract_address: str = deploy_info["address"]
    block_number: int = 0

    ex = rpc_call(
        "starknet_getTransactionByBlockNumberAndIndex", params={
            "block_number": block_number,
            "index": 99999
        }
    )

    assert ex["error"] == {
        "code": 27,
        "message": "Invalid transaction index in a block"
    }


def test_get_transaction_receipt():
    deploy_balance_contract()
    invoke_info = deploy_invoke_contract()
    transaction_hash: str = invoke_info["transaction_hash"]

    resp = rpc_call(
        "starknet_getTransactionReceipt", params={
            "transaction_hash": transaction_hash
        }
    )
    receipt = resp["result"]

    assert receipt == {
        "txn_hash": pad_zero(transaction_hash),
        "status": "ACCEPTED_ON_L2",
        "statusData": "",
        "messages_sent": [],
        "l1_origin_message": None,
        "events": [],
        "actual_fee": "0x0"
    }


def test_get_transaction_receipt_on_incorrect_hash():
    ex = rpc_call(
        "starknet_getTransactionReceipt", params={
            "transaction_hash": "0x0"
        }
    )

    assert ex["error"] == {
        "code": 25,
        "message": "Invalid transaction hash"
    }


def test_get_code():
    deploy_info = deploy_balance_contract()
    contract_address: str = deploy_info["address"]

    resp = rpc_call(
        "starknet_getCode", params={"contract_address": contract_address}
    )
    code = resp["result"]

    assert "bytecode" in code
    assert isinstance(code["bytecode"], list)
    assert len(code["bytecode"]) != 0
    assert "abi" in code
    assert isinstance(code["abi"], str)
    assert "abi" != ""


def test_get_code_raises_on_incorrect_contract():
    ex = rpc_call(
        "starknet_getCode", params={"contract_address": "0x0"}
    )

    assert ex["error"] == {
        "code": 20,
        "message": "Contract not found"
    }


def test_get_block_transaction_count_by_hash():
    deploy_balance_contract()
    block = call_test_client("get_block", blockNumber=0)
    block_hash: str = block["block_hash"]

    resp = rpc_call(
        "starknet_getBlockTransactionCountByHash", params={"block_hash": block_hash}
    )
    count = resp["result"]

    assert count == 1


def test_get_block_transaction_count_by_hash_raises_on_incorrect_hash():
    ex = rpc_call(
        "starknet_getBlockTransactionCountByHash", params={"block_hash": "0x0"}
    )

    assert ex["error"] == {
        "code": 24,
        "message": "Invalid block hash"
    }


def test_get_block_transaction_count_by_number():
    deploy_balance_contract()
    block_number: int = 0

    resp = rpc_call(
        "starknet_getBlockTransactionCountByNumber", params={"block_number": block_number}
    )
    count = resp["result"]

    assert count == 1


def test_get_block_transaction_count_by_number_raises_on_incorrect_number():
    ex = rpc_call(
        "starknet_getBlockTransactionCountByNumber", params={"block_number": 99999}
    )

    assert ex["error"] == {
        "code": 26,
        "message": "Invalid block number"
    }


def test_call():
    deploy_info = deploy_balance_contract()
    contract_address: str = deploy_info["address"]

    resp = rpc_call(
        "starknet_call", params={
            "contract_address": contract_address,
            "entry_point_selector": str(hex(get_selector_from_name("get_balance"))),
            "calldata": [],
            "block_hash": "latest"
        }
    )
    result = resp["result"]

    assert isinstance(result["result"], list)
    assert len(result["result"]) == 1
    assert result["result"][0] == "0x0"


def test_call_raises_on_incorrect_contract_address():
    ex = rpc_call(
        "starknet_call", params={
            "contract_address": "0x07b529269b82f3f3ebbb2c463a9e1edaa2c6eea8fa308ff70b30398766a2e20c",
            "entry_point_selector": str(hex(get_selector_from_name("get_balance"))),
            "calldata": [],
            "block_hash": "latest"
        }
    )

    assert ex["error"] == {
        "code": 20,
        "message": "Contract not found"
    }


def test_call_raises_on_incorrect_selector():
    deploy_info = deploy_balance_contract()
    contract_address: str = deploy_info["address"]

    ex = rpc_call(
        "starknet_call", params={
            "contract_address": contract_address,
            "entry_point_selector": str(hex(get_selector_from_name("xxxxxxx"))),
            "calldata": [],
            "block_hash": "latest"
        }
    )

    assert ex["error"] == {
        "code": 21,
        "message": "Invalid message selector"
    }


def test_call_raises_on_invalid_calldata():
    deploy_info = deploy_balance_contract()
    contract_address: str = deploy_info["address"]

    ex = rpc_call(
        "starknet_call", params={
            "contract_address": contract_address,
            "entry_point_selector": str(hex(get_selector_from_name("get_balance"))),
            "calldata": ["a", "b", "123"],
            "block_hash": "latest"
        }
    )

    assert ex["error"] == {
        "code": 22,
        "message": "Invalid call data"
    }


# This test will fail since we are throwing a custom error block_hash different from `latest`
@pytest.mark.xfail
def test_call_raises_on_incorrect_block_hash():
    deploy_info = deploy_balance_contract()
    contract_address: str = deploy_info["address"]

    ex = rpc_call(
        "starknet_call", params={
            "contract_address": contract_address,
            "entry_point_selector": str(hex(get_selector_from_name("get_balance"))),
            "calldata": [],
            "block_hash": "0x0"
        }
    )

    assert ex["error"] == {
        "code": 24,
        "message": "Invalid block hash"
    }