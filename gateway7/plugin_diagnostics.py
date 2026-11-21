"""Core-authored authoring diagnostics without exception text or input values."""

from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from gateway7.errors import StartupError


class PluginDiagnosticError(StartupError):
    def __init__(self, message: str, issues: list[dict[str, Any]]) -> None:
        self.issues = issues
        super().__init__(message)


def issue(
    code: str,
    path: str,
    message: str,
    hint: str,
    *,
    line: int | None = None,
    file: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "hint": hint,
        "line": line,
        "file": file,
    }


def diagnostic(
    message: str,
    code: str,
    path: str,
    hint: str,
    *,
    line: int | None = None,
    file: str | None = None,
) -> PluginDiagnosticError:
    return PluginDiagnosticError(message, [issue(code, path, message, hint, line=line, file=file)])


def validation_issues(
    error: ValidationError, *, model: type[BaseModel], prefix: str, file: str | None = None
) -> list[dict[str, Any]]:
    result = []
    for entry in error.errors(include_input=False, include_context=False, include_url=False)[:32]:
        current: Any = model
        path = [prefix] if prefix else []
        field = None
        for component in entry.get("loc", ()):
            if isinstance(component, int):
                path.append(str(component) if 0 <= component <= 10000 else "<index>")
                arguments = get_args(current)
                current = arguments[0] if arguments else None
            elif (
                isinstance(current, type)
                and issubclass(current, BaseModel)
                and component in current.model_fields
            ):
                path.append(component)
                field = current.model_fields[component]
                current = field.annotation
                # Optional fields can retain their declared nested model.
                if get_origin(current) in (Union, UnionType):
                    nested = [
                        item
                        for item in get_args(current)
                        if isinstance(item, type) and issubclass(item, BaseModel)
                    ]
                    if len(nested) == 1:
                        current = nested[0]
            else:
                path.append("<unknown>")
                break
        kind = entry.get("type")
        if kind == "missing":
            code, message, hint = (
                "field_required",
                "A required field is missing",
                "Add the field declared by the settings schema",
            )
        elif kind == "extra_forbidden":
            code, message, hint = (
                "field_unknown",
                "An unknown field is present",
                "Use only fields declared by the settings schema",
            )
        elif kind in (
            "int_type",
            "float_type",
            "bool_type",
            "string_type",
            "list_type",
            "dict_type",
            "model_type",
        ):
            code, message, hint = (
                "field_type",
                "A field has the wrong type",
                "Use the declared type; string-to-number coercion is disabled",
            )
        elif kind in ("string_too_long", "too_long", "string_too_short", "too_short"):
            bound_name = "max_length" if kind in ("string_too_long", "too_long") else "min_length"
            bounds = [
                getattr(constraint, bound_name, None)
                for constraint in (field.metadata if field is not None else [])
            ]
            bound = next(
                (value for value in bounds if type(value) is int and 0 <= value <= 10_000_000), None
            )
            code, message = "field_size", "A field exceeds its declared size constraints"
            hint = (
                ("Use at most " if bound_name == "max_length" else "Use at least ")
                + str(bound)
                + " characters/items"
                if bound is not None
                else "Check the documented field size bound"
            )
        else:
            code, message, hint = (
                "field_invalid",
                "A field fails its declared constraints",
                "Check the field type, allowed values and bounds in the settings schema",
            )
        result.append(issue(code, ".".join(path), message, hint, file=file))
    return result
