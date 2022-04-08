"""
Account class and its predefined constants.
"""

from starkware.cairo.lang.vm.crypto import pedersen_hash
from starkware.solidity.utils import load_nearby_contract
from starkware.starknet.business_logic.state.objects import ContractState, ContractCarriedState
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.contract_definition import ContractDefinition
from starkware.starknet.services.api.gateway.contract_address import calculate_contract_address_from_hash
from starkware.starknet.storage.starknet_storage import StorageLeaf
from starkware.starknet.testing.starknet import Starknet
from starkware.starknet.testing.contract import StarknetContract

from starkware.python.utils import to_bytes

CONTRACT_PATH = "accounts_artifacts/OpenZeppelin/0.1.0/Account.cairo/Account"
# HASH = compute_contract_hash(contract_definition=DEFINITION))
HASH = 361479646297615797917493841430922492724680358320444679508058603177506550951
HASH_BYTES = to_bytes(HASH)
SALT = 20

class Account: # TODO inherit from StarknetContract
    """Account contract wrapper."""

    DEFINITION = ContractDefinition.load(load_nearby_contract(CONTRACT_PATH))

    def __init__(self, private_key: int, public_key: int, initial_balance: int):
        self.private_key = private_key
        self.public_key = public_key
        self.address = calculate_contract_address_from_hash(
            salt=SALT,
            contract_hash=HASH,
            constructor_calldata=[public_key],
            caller_address=0
        )
        self.initial_balance = initial_balance
        self._abi_function_mapping = {
            abi_entry["name"]: abi_entry for abi_entry in Account.DEFINITION.abi if abi_entry["type"] == "function"
        }

    async def deploy(self, starknet: Starknet):
        """Deploy this account."""
        account_carried_state = starknet.state.state.contract_states[self.address]
        account_state = account_carried_state.state
        assert not account_state.initialized

        starknet.state.state.contract_definitions[HASH_BYTES] = Account.DEFINITION

        newly_deployed_account_state = await ContractState.create(
            contract_hash=HASH_BYTES,
            storage_commitment_tree=account_state.storage_commitment_tree
        )

        starknet.state.state.contract_states[self.address] = ContractCarriedState(
            state=newly_deployed_account_state,
            storage_updates={
                get_selector_from_name("public_key"): StorageLeaf(self.public_key)
            }
        )

        # set initial balance
        fee_token_address = starknet.state.general_config.fee_token_address
        fee_token_storage_updates = starknet.state.state.contract_states[fee_token_address].storage_updates

        balance_address = pedersen_hash(get_selector_from_name("ERC20_balances"), self.address)
        fee_token_storage_updates[balance_address] = StorageLeaf(self.initial_balance)
        # TODO uint256 requires additional value (this only probably set low; high needs setting as well)
