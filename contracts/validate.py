"""Standard-library validator for the HerBiz contract schemas (JSON Schema 2020-12 subset; no third-party packages).

    python3 contracts/validate.py <schema.json> <payload.json>     # prints OK or the errors; exit 1 on errors

Supported keywords (the only ones contracts/build_schemas.py emits; tests/test_contracts.py enforces this):
type, const, enum, required, properties, additionalProperties, items, minItems, maxItems, uniqueItems, pattern,
minLength, minimum, if/then, allOf, oneOf, and the annotations $schema, $id, title, description.
Anything else in a schema raises UnsupportedKeyword, so a schema can never be silently under-checked.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SUPPORTED = {"type", "const", "enum", "required", "properties", "additionalProperties", "items", "minItems", "maxItems",
             "uniqueItems", "pattern", "minLength", "minimum", "if", "then", "allOf", "oneOf"}
ANNOTATIONS = {"$schema", "$id", "title", "description"}


class UnsupportedKeyword(ValueError):
    pass


def _is_type(x, t: str) -> bool:
    if t == "object":
        return isinstance(x, dict)
    if t == "array":
        return isinstance(x, list)
    if t == "string":
        return isinstance(x, str)
    if t == "boolean":
        return isinstance(x, bool)
    if t == "integer":
        return isinstance(x, int) and not isinstance(x, bool)
    if t == "number":
        return isinstance(x, (int, float)) and not isinstance(x, bool)
    if t == "null":
        return x is None
    raise UnsupportedKeyword(f"type {t}")


def _eq(a, b) -> bool:
    """JSON equality: 1 == 1.0, but True != 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def errors(schema: dict, x, path: str = "$") -> list[str]:
    unknown = set(schema) - SUPPORTED - ANNOTATIONS
    if unknown:
        raise UnsupportedKeyword(f"{path}: {sorted(unknown)}")
    out: list[str] = []
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(x, t) for t in ts):
            return [f"{path}: expected type {ts}, got {type(x).__name__}"]
    if "const" in schema and not _eq(x, schema["const"]):
        out.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and not any(_eq(x, e) for e in schema["enum"]):
        out.append(f"{path}: {x!r} not in {schema['enum']}")
    if isinstance(x, str):
        if "minLength" in schema and len(x) < schema["minLength"]:
            out.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], x):
            out.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(x, (int, float)) and not isinstance(x, bool) and "minimum" in schema and x < schema["minimum"]:
        out.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(x, dict):
        for k in schema.get("required", []):
            if k not in x:
                out.append(f"{path}: missing required '{k}'")
        props = schema.get("properties", {})
        for k, v in x.items():
            if k in props:
                out += errors(props[k], v, f"{path}.{k}")
            elif "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is False:
                    out.append(f"{path}: unexpected field '{k}'")
                elif isinstance(ap, dict):
                    out += errors(ap, v, f"{path}.{k}")
    if isinstance(x, list):
        if "minItems" in schema and len(x) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(x) > schema["maxItems"]:
            out.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(i, sort_keys=True) for i in x]
            if len(seen) != len(set(seen)):
                out.append(f"{path}: items not unique")
        if "items" in schema:
            for i, v in enumerate(x):
                out += errors(schema["items"], v, f"{path}[{i}]")
    if "if" in schema:
        if not errors(schema["if"], x, path):
            if "then" in schema:
                out += errors(schema["then"], x, path)
    for sub in schema.get("allOf", []):
        out += errors(sub, x, path)
    if "oneOf" in schema:
        n = sum(1 for sub in schema["oneOf"] if not errors(sub, x, path))
        if n != 1:
            out.append(f"{path}: matches {n} of oneOf (exactly 1 required)")
    return out


def load(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if len(a) != 2:
        print(__doc__)
        return 2
    errs = errors(load(a[0]), load(a[1]))
    print("OK" if not errs else "\n".join(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
