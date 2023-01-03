import copy
import json
from typing import Any, Dict

from jsonschema import validate

from test.support.assertions import load_json_schema

specs_json = load_json_schema("starknet_api_openrpc.json")
schemas = specs_json["components"]["schemas"]
methods = {method["name"]: method for method in specs_json["methods"]}

for schema in schemas.values():
    if "required" not in schema and "properties" in schema:
        schema["required"] = [prop for prop in schema["properties"].keys()]
    if "allOf" in schema or "anyOf" in schema:
        schema["unevaluatedProperties"] = False


def assert_valid_rpc_schema(data: Dict[str, Any], method_name: str):
    schema = _schema_for_method(method_name)
    validate(data, schema=schema)


def _schema_for_method(name: str) -> Dict[str, Any]:
    """
    Return a dict structured like
    {
        // base schema
        "components": {
            "schemas": {
                // ...
            }
        }
    }
    for the use in json schema validation
    """
    # base_schema = schemas[name]
    base_schema = methods[name]["result"]["schema"]

    if all(i not in base_schema for i in ("allOf", "anyOf", "oneOf")):
        base_schema["additionalProperties"] = False

    # new_schemas = copy.deepcopy(schemas)
    # del new_schemas[name]

    return {
        **base_schema,
        "components": {
            "schemas": schemas
        }
    }
