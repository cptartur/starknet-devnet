"""
Contains logic for instantiating a custom Starknet.
"""

import random

from starkware.cairo.lang.vm.crypto import pedersen_hash
from starkware.crypto.signature.signature import get_random_private_key, private_to_stark_key
from starkware.contracts.utils import load_nearby_contract
from starkware.starknet.business_logic.state_objects import ContractState, ContractCarriedState
from starkware.starknet.core.os.contract_hash import compute_contract_hash
from starkware.starknet.definitions.general_config import StarknetGeneralConfig
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.contract_definition import ContractDefinition
from starkware.starknet.services.api.gateway.contract_address import calculate_contract_address_from_hash
from starkware.starknet.storage.starknet_storage import StorageLeaf
from starkware.starknet.testing.starknet import Starknet
from starkware.python.utils import to_bytes

import time

erc20_start = time.time()
fee_token_definition = ContractDefinition.load(load_nearby_contract("ERC20"))
fee_token_hash = compute_contract_hash(contract_definition=fee_token_definition)
print(time.time() - erc20_start)

account_start = time.time()
account_definition = ContractDefinition.load(load_nearby_contract("accounts_artifacts/OpenZeppelin/0.1.0/Account.cairo/Account"))
account_hash = compute_contract_hash(contract_definition=account_definition)
print(time.time() - account_start)

def get_general_config(fee_token_address: int):
    """Return a StarknetGeneralConfig with the fee_token_address assigned."""

    return StarknetGeneralConfig.load({
        "event_commitment_tree_height": 64,
        "global_state_commitment_tree_height": 251,
        'gas_price': 100000000000,
        'starknet_os_config': {
            'chain_id': 'TESTNET',
            'fee_token_address': hex(fee_token_address)
        },
        'contract_storage_commitment_tree_height': 251,
        'cairo_resource_fee_weights': {
            'n_steps': 0.05,
            'pedersen_builtin': 0.4,
            'range_check_builtin': 0.4,
            'ecdsa_builtin': 25.6,
            'bitwise_builtin': 12.8,
            'output_builtin': 0.0,
            'ec_op_builtin': 0.0
        }, 'invoke_tx_max_n_steps': 1000000,
        'sequencer_address': '0x37b2cd6baaa515f520383bee7b7094f892f4c770695fc329a8973e841a971ae',
        'tx_version': 0,
        'tx_commitment_tree_height': 64
    })

async def generate_accounts(starknet: Starknet, n_accounts: int, initial_balance: int, seed: int):
    """
    Generate `n_accounts` accounts with `inital_balance` at `fee_token_address`.
    """
    account_salt = 20
    random_generator = random.Random()
    if seed:
        random_generator.seed(seed)

    for i in range(1, n_accounts + 1):
        private_key = random_generator.randint(1, 1e18)
        public_key = private_to_stark_key(private_key)

        account_constructor_calldata = [
            public_key
        ]
        print(f"{i})")
        print(f"{public_key}, {private_key}")
        account_address = calculate_contract_address_from_hash(
            salt=account_salt,
            contract_hash=account_hash,
            constructor_calldata=account_constructor_calldata,
            caller_address=0
        )

        account_carried_state = starknet.state.state.contract_states[account_address]
        account_state = account_carried_state.state
        assert not account_state.initialized

        starknet.state.state.contract_definitions[account_hash] = account_definition

        newly_deployed_account_state = await ContractState.create(
            contract_hash=to_bytes(account_hash),
            storage_commitment_tree=account_state.storage_commitment_tree
        )

        fee_token_address = starknet.state.general_config.fee_token_address
        starknet.state.state.contract_states[fee_token_address] = ContractCarriedState(
            state=newly_deployed_account_state,
            storage_updates={
                # TODO set public key
            }
        )

        fee_token_storage_updates = starknet.state.state.contract_states[fee_token_address].storage_updates
        # TODO increase balance
        fee_token_storage_updates[pedersen_hash(get_selector_from_name("ERC20_balances"), 0)] = StorageLeaf(123)

async def create_custom_starknet():
    """
    Create a wrapper of Starknet.empty() with custom configuration and predeployed contracts.
    """

    fee_token_salt = 10
    constructor_calldata = [
        42, # name
        2, # symbol
        18, # decimals
        1000, # initial supply - low
        0, # initial supply - high
        1, # recipient
    ]

    fee_token_address = calculate_contract_address_from_hash(
        salt=fee_token_salt,
        contract_hash=fee_token_hash,
        constructor_calldata=constructor_calldata,
        caller_address=0
    )

    starknet = await Starknet.empty(general_config=get_general_config(fee_token_address))

    fee_token_carried_state = starknet.state.state.contract_states[fee_token_address]
    fee_token_state = fee_token_carried_state.state
    assert not fee_token_state.initialized

    starknet.state.state.contract_definitions[fee_token_hash] = fee_token_definition

    newly_deployed_fee_token_state = await ContractState.create(
        contract_hash=to_bytes(fee_token_hash),
        storage_commitment_tree=fee_token_state.storage_commitment_tree
    )

    starknet.state.state.contract_states[fee_token_address] = ContractCarriedState(
        state=newly_deployed_fee_token_state,
        storage_updates={}
    )

    account_generation_start = time.time()
    await generate_accounts(starknet, n_accounts=20, initial_balance=1000, seed=42)
    print("account generation took:", time.time() - account_generation_start)

    return starknet
