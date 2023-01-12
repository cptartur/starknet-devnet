"""
Test RPC schema validation
"""

from test.rpc.rpc_utils import rpc_call

import pytest
from starkware.starknet.public.abi import get_selector_from_name

from starknet_devnet.blueprints.rpc.structures.types import RpcErrorCode
from starknet_devnet.blueprints.rpc.utils import rpc_felt


@pytest.mark.usefixtures("run_devnet_in_background")
@pytest.mark.parametrize(
    "params",
    (
        {
            "request": {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
        },
        {
            "block_id": "latest",
        },
        {},
        {
            "request": {
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "block_id": "latest",
        },
        {
            "request": {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": "0x1234",
            },
            "block_id": "latest",
        },
        {
            "request": {
                "contract_address": 1324,
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "block_id": "latest",
        },
        {
            "request": {
                "contract_address": "0x01",
                "entry_point_selector": ["0x01", "0x02"],
                "calldata": [],
            },
            "block_id": "latest",
        },
    ),
)
def test_schema_raises_on_invalid_kwargs(params):
    """
    Call contract
    """
    resp = rpc_call("starknet_call", params=params)

    assert "error" in resp
    error = resp["error"]

    print(error)
    assert error["code"] == RpcErrorCode.INVALID_PARAMS.value


@pytest.mark.usefixtures("run_devnet_in_background")
@pytest.mark.parametrize(
    "params",
    (
        [
            {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            }
        ],
        [
            "latest",
        ],
        [],
        [
            {
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "latest",
        ],
        [
            {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": "0x1234",
            },
            "latest",
        ],
        [
            {
                "contract_address": 1324,
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "latest",
        ],
        [
            {
                "contract_address": "0x01",
                "entry_point_selector": ["0x01", "0x02"],
                "calldata": [],
            },
            "latest",
        ],
        [
            "latest",
            {
                "contract_address": "0x01",
                "entry_point_selector": "0x01",
                "calldata": [],
            },
        ],
    ),
)
def test_schema_raises_on_invalid_args(params):
    """
    Call contract
    """
    resp = rpc_call("starknet_call", params=params)

    assert "error" in resp
    error = resp["error"]

    assert error["code"] == RpcErrorCode.INVALID_PARAMS.value


@pytest.mark.usefixtures("run_devnet_in_background")
@pytest.mark.parametrize(
    "params",
    (
        {
            "request": {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "block_id": "latest",
        },
        {
            "block_id": "latest",
            "request": {
                "contract_address": "0x01",
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
        },
    ),
)
def test_schema_does_not_raise_on_correct_kwargs(params):
    """
    Call contract
    """

    resp = rpc_call("starknet_call", params=params)

    # Error will be raised because address is correctly formatted but incorrect
    error = resp["error"]
    print(error)
    assert all(error["code"] != code.value for code in RpcErrorCode)


@pytest.mark.usefixtures("run_devnet_in_background")
def test_schema_does_not_raise_on_correct_args(deploy_info):
    """
    Call contract
    """
    contract_address: str = deploy_info["address"]

    resp = rpc_call(
        "starknet_call",
        params=[
            {
                "contract_address": rpc_felt(contract_address),
                "entry_point_selector": rpc_felt(get_selector_from_name("get_balance")),
                "calldata": [],
            },
            "latest",
        ],
    )
    assert "error" not in resp
