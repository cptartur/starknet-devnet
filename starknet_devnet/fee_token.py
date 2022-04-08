"""
Fee token and its predefined constants.
"""

from starkware.solidity.utils import load_nearby_contract
from starkware.starknet.services.api.contract_definition import ContractDefinition
from starkware.starknet.services.api.gateway.contract_address import calculate_contract_address_from_hash
from starkware.starknet.business_logic.state.objects import ContractState, ContractCarriedState
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.storage.starknet_storage import StorageLeaf
from starkware.starknet.testing.starknet import Starknet
from starkware.python.utils import to_bytes

DEFINITION = ContractDefinition.load(load_nearby_contract("ERC20"))
# HASH = to_bytes(compute_contract_hash(contract_definition=DEFINITION))
HASH = 375899817338126263298463755162657787890597705735749339531748983767835688120
HASH_BYTES = to_bytes(HASH)
SALT = 10
CONSTRUCTOR_CALLDATA = [
    42, # name
    2, # symbol
    18, # decimals
    1000, # initial supply - low
    0, # initial supply - high
    1, # recipient
]

ADDRESS = calculate_contract_address_from_hash(
    salt=SALT,
    contract_hash=HASH,
    constructor_calldata=CONSTRUCTOR_CALLDATA,
    caller_address=0
)

async def deploy(starknet: Starknet):
    """Deploy token contract for charging fees."""

    fee_token_carried_state = starknet.state.state.contract_states[ADDRESS]
    fee_token_state = fee_token_carried_state.state
    assert not fee_token_state.initialized

    starknet.state.state.contract_definitions[HASH_BYTES] = DEFINITION
    newly_deployed_fee_token_state = await ContractState.create(
        contract_hash=HASH_BYTES,
        storage_commitment_tree=fee_token_state.storage_commitment_tree
    )

    starknet.state.state.contract_states[ADDRESS] = ContractCarriedState(
        state=newly_deployed_fee_token_state,
        storage_updates={
            # TODO check if running the constructor even needs to be simulated
            get_selector_from_name("name"): StorageLeaf(42)
            # ...
        }
    )
