"""
Shared helper — validate a loan_file dict against the shared schema.

Usage:
    from shared.schema_loader import validate_loan_file

    validate_loan_file(my_loan_file_dict)  # raises if invalid

Every agent should call this on its output before writing it back,
so contract violations get caught locally instead of at merge time.
"""

import json
from pathlib import Path

try:
    import jsonschema
except ImportError as e:
    raise ImportError(
        "jsonschema is required: pip install jsonschema"
    ) from e

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "loan_file.schema.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_loan_file(loan_file: dict) -> None:
    """Raises jsonschema.ValidationError if loan_file does not match the contract."""
    schema = load_schema()
    jsonschema.validate(instance=loan_file, schema=schema)


if __name__ == "__main__":
    # Quick manual check: validate the example fixture against the schema.
    example_path = Path(__file__).resolve().parent.parent / "schema" / "loan_file.example.json"
    with open(example_path, "r", encoding="utf-8") as f:
        example = json.load(f)
    validate_loan_file(example)
    print("loan_file.example.json is valid against loan_file.schema.json")
