from functools import lru_cache

from test.support.assertions import load_json_schema
from typing import Any, Dict, Tuple

from jsonschema import validate


# Cache the function result so schemas are not reloaded from disk on every call
@lru_cache
def load_schemas() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    specs_json = load_json_schema("starknet_api_openrpc.json")
    schemas = specs_json["components"]["schemas"]
    methods = {method["name"]: method for method in specs_json["methods"]}

    for schema in schemas.values():
        # Newer version of the rpc (above 0.45.0) have required properly defined.
        # Once we start targeting them, this can be removed.
        if "required" not in schema and "properties" in schema:
            schema["required"] = [prop for prop in schema["properties"].keys()]

        # Ensures validation fails in case of extra fields not matched by any of `allOf` / `anyOf` branches.
        if "allOf" in schema or "anyOf" in schema:
            schema["unevaluatedProperties"] = False

    return methods, schemas


def assert_valid_rpc_schema(data: Dict[str, Any], method_name: str):
    schema = _schema_for_method(method_name)
    validate(data, schema=schema)


def _schema_for_method(name: str) -> Dict[str, Any]:
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

    methods, schemas = load_schemas()
    base_schema = methods[name]["result"]["schema"]

    if all(i not in base_schema for i in ("allOf", "anyOf", "oneOf")):
        # This has to be done here, because setting additionalProperties = False in
        # load_schemas doesn't work with `allOf` etc. properly.
        base_schema["additionalProperties"] = False

    return {**base_schema, "components": {"schemas": schemas}}
