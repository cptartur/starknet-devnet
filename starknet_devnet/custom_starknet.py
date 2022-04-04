"""
Contains logic for instantiating a custom Starknet.
"""

from starkware.cairo.lang.vm.crypto import pedersen_hash
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

async def create_custom_starknet():
    """
    Create a wrapper of Starknet.empty() with custom configuration and predeployed contracts.
    """

    fee_token_definition = ContractDefinition.load(load_nearby_contract("ERC20"))
    fee_token_hash = compute_contract_hash(contract_definition=fee_token_definition)
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

    default_general_config = StarknetGeneralConfig.load({
        "event_commitment_tree_height": 64,
        "global_state_commitment_tree_height": 251,
        'gas_price': 100000000000,
        'starknet_os_config': {
            'chain_id': 'TESTNET',
            'fee_token_address': fee_token_address
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

    starknet = await Starknet.empty(general_config=default_general_config)

    fee_token_hash = compute_contract_hash(contract_definition=fee_token_definition)

    fee_token_address = calculate_contract_address_from_hash(
        salt=fee_token_salt,
        contract_hash=fee_token_hash,
        constructor_calldata=constructor_calldata,
        caller_address=0
    )

    fee_token_carried_state = starknet.state.state.contract_states[fee_token_address]
    fee_token_state = fee_token_carried_state.state
    assert not fee_token_state.initialized

    starknet.state.state.contract_definitions[fee_token_hash] = fee_token_definition

    newly_deployed_contract_state = await ContractState.create(
        contract_hash=to_bytes(fee_token_hash),
        storage_commitment_tree=fee_token_state.storage_commitment_tree
    )

    starknet.state.state.contract_states[fee_token_address] = ContractCarriedState(
        state=newly_deployed_contract_state,
        storage_updates={}
    )

    # "deploy" Account here

    # increase balance
    fee_token_storage_updates = starknet.state.state.contract_states[fee_token_address].storage_updates
    fee_token_storage_updates[pedersen_hash(get_selector_from_name("ERC20_balances"), 0)] = StorageLeaf(123)

    print("DEBUG storage_updates after", fee_token_storage_updates)
    print("DEBUG storage_updates keys after", fee_token_storage_updates.keys())

    return starknet
