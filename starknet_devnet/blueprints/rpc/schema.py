"""
Utilities for validating RPC responses against RPC specification
"""
import json
from collections import OrderedDict
from functools import lru_cache, wraps
from itertools import zip_longest
from typing import Any, Dict, List
from typing import OrderedDict as OrderedDictType
from typing import Tuple

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from starknet_devnet.blueprints.rpc.rpc_spec import RPC_SPECIFICATION
from starknet_devnet.blueprints.rpc.rpc_spec_write import RPC_SPECIFICATION_WRITE


# Cache the function result so schemas are not reloaded from disk on every call
@lru_cache
def _load_schemas() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    specs_json = json.loads(RPC_SPECIFICATION)
    schemas = specs_json["components"]["schemas"]
    methods = {method["name"]: method for method in specs_json["methods"]}

    write_specs_json = json.loads(RPC_SPECIFICATION_WRITE)
    methods = {
        **methods,
        **{method["name"]: method for method in write_specs_json["methods"]},
    }

    for schema in schemas.values():
        # Newer version of the RPC (above 0.45.0) has properly defined `required` fields.
        # Once we start targeting them, this can be removed.
        #
        # NOTE: This does not add `required` to all schemas that should have it, i.e. it fails to add `required`
        # to nested objects. This causes validation to be incomplete in these cases.
        if "required" not in schema and "properties" in schema:
            schema["required"] = list(schema["properties"].keys())

        # Ensures validation fails in case of extra fields not matched by any of `allOf` / `anyOf` branches.
        if any(i for i in ("allOf", "anyOf", "oneOf")):
            schema["unevaluatedProperties"] = False

    return methods, schemas


def _response_schema_for_method(name: str) -> Dict[str, Any]:
    """
    Return a dict with correct structure for jsonschema validation.

    {
        // base schema
        // ...
        "components": {
            "schemas": {
                // rest of the schemas
                // ...
            }
        }
    }

    Main "base schema" has to be placed in the "top-level" of the dictionary, so jsonschema
    knows against what of the multiple schemas present in the RPC spec to verify.

    RPC spec is currently formatted in the way, that every `$ref` is made with respect to
    #/components/schemas/SCHEMA_NAME
    The dict with schemas has to follow the same structure using
    nested dictionaries.
    """

    methods, schemas = _load_schemas()
    base_schema = methods[name]["result"]["schema"]

    if not any(i in base_schema for i in ("allOf", "anyOf", "oneOf")):
        # This has to be done here, because setting additionalProperties = False in
        # load_schemas doesn't work with `allOf` etc. properly.
        base_schema["additionalProperties"] = False

    return {**base_schema, "components": {"schemas": schemas}}


def _request_schemas_for_method(name: str) -> OrderedDictType[str, Any]:
    """
    Return a dict with correct structure for jsonschema validation.

    {
        "schema1": { // schema 1 },
        "schema2: { // schema 2 },
        // ...
        "components": {
            "schemas": {
                // rest of the schemas
                // ...
            }
        }
    }

    See _response_schema_for_method docstring for more detailed explanation.
    """
    methods, schemas = _load_schemas()
    params_json: List[Dict[str, Any]] = methods[name]["params"]

    params = []
    request_schemas = OrderedDict()
    for param in params_json:
        name = param["name"]
        params.append(name)
        schema = {**param["schema"], "components": {"schemas": schemas}}
        request_schemas[name] = schema

    return request_schemas


def _construct_method_name(method_name: str) -> str:
    if "starknet_" not in method_name:
        method_name = "starknet_" + method_name
    return method_name


def assert_valid_rpc_schema(data: Dict[str, Any], method_name: str):
    """
    Check if rpc response is valid against the schema for given method name
    """
    schema = _response_schema_for_method(_construct_method_name(method_name))
    validate(data, schema=schema)


def assert_valid_rpc_request(*args, method_name: str, **kwargs):
    """
    Validate if RPC request (parameters) is correct.

    Raise ValidationError if not.
    """
    schemas = _request_schemas_for_method(_construct_method_name(method_name))

    if args and kwargs:
        raise ValueError("Cannot validate schemas with both args and kwargs provided.")

    if args:
        if len(args) > len(schemas):
            raise ValidationError("Too many arguments provided.")

        for name, arg in zip_longest(schemas.keys(), args, fillvalue="missing"):
            if arg == "missing":
                raise ValidationError(f"Missing arg for {name}.")

            validate(arg, schemas[name])
        return

    if kwargs:
        if len(kwargs) > len(schemas):
            raise ValidationError("Too many arguments provided.")

        for name, schema in schemas.items():
            if name not in kwargs:
                raise ValidationError(f"Missing kwarg for {name}.")

            value = kwargs[name]
            validate(value, schema)
        return

    if length := len(schemas) != 0:
        raise ValidationError(
            f"0 arguments provided to function expecting {length} arguments."
        )


class ParamsValidationErrorWrapper(Exception):
    """
    Wrapper for ValidationError raised during request validation
    """

    def __init__(self, err: ValidationError):
        super().__init__("Failed to validate schema for params.")
        self.validation_error = err


class ResponseValidationErrorWrapper(Exception):
    """
    Wrapper for ValidationError raised during response validation
    """

    def __init__(self, err: ValidationError):
        super().__init__("Failed to validate schema for response.")
        self.validation_error = err


def validate_schema(method_name: str):
    """
    Decorator ensuring that call to rpc method and its response are valid
    in respect to RPC specification schemas.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                assert_valid_rpc_request(*args, **kwargs, method_name=method_name)
            except ValidationError as err:
                raise ParamsValidationErrorWrapper(err) from err

            result = await func(*args, **kwargs)

            try:
                assert_valid_rpc_schema(result, method_name)
            except ValidationError as err:
                raise ResponseValidationErrorWrapper(err) from err

            return result

        return wrapper

    return decorator
