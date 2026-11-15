"""Generate the checked-in OpenAPI artifact and TypeScript transport types."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app


def _schema_type(schema: dict[str, Any] | bool | None) -> str:
    if schema is None or schema is True or schema == {}:
        return "JSONValue"
    if schema is False:
        return "never"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema or "oneOf" in schema:
        variants = schema.get("anyOf", schema.get("oneOf", []))
        return " | ".join(dict.fromkeys(_schema_type(item) for item in variants))
    if "allOf" in schema:
        return " & ".join(_schema_type(item) for item in schema["allOf"])

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        variants = [{**schema, "type": item} for item in schema_type]
        return " | ".join(dict.fromkeys(_schema_type(item) for item in variants))
    if schema_type == "array":
        return f"Array<{_schema_type(schema.get('items'))}>"
    if schema_type == "object":
        properties = schema.get("properties", {})
        if properties:
            required = set(schema.get("required", []))
            lines = [
                f"  {json.dumps(key)}{'?' if key not in required else ''}: {_schema_type(value)};"
                for key, value in properties.items()
            ]
            return "{\n" + "\n".join(lines) + "\n}"
        additional = schema.get("additionalProperties")
        if additional is not None:
            return f"Record<string, {_schema_type(additional)}>"
        return "Record<string, JSONValue>"
    if schema_type == "string":
        return "string"
    if schema_type == "integer" or schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    return "JSONValue"


def _content_type(openapi_response: dict[str, Any]) -> str:
    content = openapi_response.get("content", {})
    schemas = [entry.get("schema") for entry in content.values()]
    return " | ".join(dict.fromkeys(_schema_type(schema) for schema in schemas)) or "void"


def _object_type(parameters: list[dict[str, Any]], location: str) -> str:
    selected = [item for item in parameters if item.get("in") == location]
    if not selected:
        return "Record<never, never>"
    lines = []
    for parameter in selected:
        optional = "" if parameter.get("required") else "?"
        lines.append(
            f"  {json.dumps(parameter['name'])}{optional}: {_schema_type(parameter.get('schema'))};"
        )
    return "{\n" + "\n".join(lines) + "\n}"


def _typescript(openapi: dict[str, Any]) -> str:
    components = openapi["components"]["schemas"]
    lines = [
        "/* Generated from backend/openapi.json. Do not edit by hand. */",
        "export type JSONValue = string | number | boolean | null | JSONValue[] | { [key: string]: JSONValue };",
        "",
    ]
    for name, schema in components.items():
        if name == "JSONValue":
            continue
        lines.extend([f"export type {name} = {_schema_type(schema)};", ""])

    lines.extend(["export interface ApiOperations {"])
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_key = f"{method.upper()} {path}"
            parameters = operation.get("parameters", [])
            request_body = operation.get("requestBody", {})
            request_schema = None
            for media_type in (
                "application/json",
                "application/x-www-form-urlencoded",
                "multipart/form-data",
            ):
                entry = request_body.get("content", {}).get(media_type)
                if entry:
                    request_schema = entry.get("schema")
                    break
            responses = operation.get("responses", {})
            response_lines = []
            for status, response in responses.items():
                response_lines.append(f"      {json.dumps(status)}: {_content_type(response)};")
            lines.extend(
                [
                    f"  {json.dumps(operation_key)}: {{",
                    f"    path: {_object_type(parameters, 'path')};",
                    f"    query: {_object_type(parameters, 'query')};",
                    f"    request: {_schema_type(request_schema) if request_schema is not None else 'never'};",
                    "    responses: {",
                    *response_lines,
                    "    };",
                    "  };",
                ]
            )
    lines.extend(
        [
            "}",
            "",
            "export type ApiOperationName = keyof ApiOperations;",
            "export type ApiPath<K extends ApiOperationName> = ApiOperations[K]['path'];",
            "export type ApiQuery<K extends ApiOperationName> = ApiOperations[K]['query'];",
            "export type ApiRequest<K extends ApiOperationName> = ApiOperations[K]['request'];",
            "export type ApiResponse<K extends ApiOperationName> = ApiOperations[K]['responses'][keyof ApiOperations[K]['responses']];",
            "export type ApiSuccessResponse<K extends ApiOperationName> = {",
            "  [S in keyof ApiOperations[K]['responses']]: `${S & (string | number)}` extends `2${string}`",
            "    ? ApiOperations[K]['responses'][S]",
            "    : never",
            "}[keyof ApiOperations[K]['responses']];",
            "",
        ]
    )
    return "\n".join(lines)


def _artifacts() -> dict[Path, str]:
    openapi = app.openapi()
    openapi_text = json.dumps(openapi, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    typescript_text = _typescript(openapi)
    return {
        BACKEND_DIR / "openapi.json": openapi_text,
        REPOSITORY_DIR / "frontend" / "src" / "types" / "api.ts": typescript_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = parser.parse_args()
    stale: list[str] = []
    for path, content in _artifacts().items():
        relative = path.relative_to(REPOSITORY_DIR)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(relative))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"generated {relative}")
    if stale:
        print("generated contract is stale: " + ", ".join(stale), file=sys.stderr)
        return 1
    if args.check:
        print("OpenAPI and TypeScript contract are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
