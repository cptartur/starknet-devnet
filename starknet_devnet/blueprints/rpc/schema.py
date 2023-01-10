"""
Utilities for validating RPC responses against RPC specification
"""
import json
from dataclasses import dataclass
from functools import lru_cache, wraps
from typing import Any, Dict, List, Tuple

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
    Return a dict structured like
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
    for the use in json schema validation.
    """

    methods, schemas = _load_schemas()
    base_schema = methods[name]["result"]["schema"]

    if all(i not in base_schema for i in ("allOf", "anyOf", "oneOf")):
        # This has to be done here, because setting additionalProperties = False in
        # load_schemas doesn't work with `allOf` etc. properly.
        base_schema["additionalProperties"] = False

    return {**base_schema, "components": {"schemas": schemas}}


@dataclass
class RequestSchema:
    """
    Return type of _request_schemas_for_method function
    """

    params: List[str]
    schemas: Dict[str, Any]


def _request_schemas_for_method(name: str) -> RequestSchema:
    methods, schemas = _load_schemas()
    params_json: List[Dict[str, Any]] = methods[name]["params"]

    params = []
    request_schemas = {}
    for param in params_json:
        name = param["name"]
        params.append(name)
        schema = {**param["schema"], "components": {"schemas": schemas}}
        request_schemas[name] = schema

    return RequestSchema(params, request_schemas)


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

    for arg, name in zip(args, schemas.params):
        validate(arg, schemas.schemas[name])

    for name, value in kwargs.items():
        validate(value, schemas.schemas[name])


class ParamsValidationErrorWrapper(Exception):
    """
    Wrapper for ValidationError raised during request validation
    """

    def __init__(self, err: ValidationError):
        super().__init__()
        self.validation_error = err


class ResponseValidationErrorWrapper(Exception):
    """
    Wrapper for ValidationError raised during response validation
    """

    def __init__(self, err: ValidationError):
        super().__init__()
        self.validation_error = err


def require_valid_request_and_response(method_name: str):
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
