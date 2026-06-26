from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from acodex.cli.tools.models import ToolArgumentsError

ARGUMENT_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
HELP_TOKEN = "--help"  # noqa: S105 - CLI help flag, not a password.
OPTION_PREFIX = "--"
PROPERTIES_KEY = "properties"


@dataclass(frozen=True, slots=True)
class ToolArgumentsParser:
    """Parse dynamic MCP tool arguments from CLI tokens."""

    def parse(
        self,
        tokens: list[str],
        *,
        args_json: str | None = None,
        args_json_file: Path | None = None,
    ) -> dict[str, Any]:
        """Parse CLI tokens and optional JSON sources into a tool arguments object.

        Returns:
            Parsed JSON-compatible tool arguments.

        Raises:
            ToolArgumentsError: If the CLI tokens or JSON sources are invalid.

        """
        json_arguments = JSONArgumentSource().load(
            args_json=args_json,
            args_json_file=args_json_file,
        )
        token_arguments = OptionTokenParser().parse(tokens)
        duplicates = sorted(set(json_arguments).intersection(token_arguments))
        if duplicates:
            raise ToolArgumentsError("Duplicate tool argument: {}".format(", ".join(duplicates)))
        return {**json_arguments, **token_arguments}

    def is_help_request(self, tokens: list[str]) -> bool:
        """Return whether the dynamic tool arguments request tool help."""
        return HELP_TOKEN in tokens


@dataclass(frozen=True, slots=True)
class JSONArgumentSource:
    """Read a JSON object from CLI text or a file."""

    def load(
        self,
        *,
        args_json: str | None,
        args_json_file: Path | None,
    ) -> dict[str, Any]:
        """Return a JSON object from one optional source."""
        if args_json is not None and args_json_file is not None:
            raise ToolArgumentsError("--args-json and --args-json-file cannot be used together")
        if args_json is None and args_json_file is None:
            return {}
        if args_json_file is not None:
            return self._load_file(args_json_file)
        return self._json_object(args_json or "", source="--args-json")

    def _load_file(self, args_json_file: Path) -> dict[str, Any]:
        try:
            return self._json_object(
                args_json_file.read_text(encoding="utf-8"),
                source=str(args_json_file),
            )
        except OSError as exc:
            raise ToolArgumentsError(
                f"Could not read tool arguments from {args_json_file}: {exc}",
            ) from exc

    def _json_object(self, raw_json: str, *, source: str) -> dict[str, Any]:
        try:
            json_payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ToolArgumentsError(
                f"{source} must contain valid JSON: {exc.msg}",
            ) from exc
        if not isinstance(json_payload, dict):
            raise ToolArgumentsError(f"{source} must contain a JSON object")
        return cast("dict[str, Any]", json_payload)


@dataclass(frozen=True, slots=True)
class OptionTokenParser:
    """Parse ``--key value`` and ``--key=value`` tool arguments."""

    def parse(self, tokens: list[str]) -> dict[str, Any]:
        """Return parsed top-level tool arguments."""
        token_stream = OptionTokenStream(tokens)
        token_arguments: dict[str, Any] = {}
        while token_stream.has_next:
            option_key, option_value = token_stream.next_argument()
            self._ensure_unique(option_key, token_arguments)
            token_arguments[option_key] = option_value
        return token_arguments

    def _ensure_unique(self, option_key: str, token_arguments: dict[str, Any]) -> None:
        if option_key in token_arguments:
            raise ToolArgumentsError(f"Duplicate tool argument: {option_key}")


@dataclass(slots=True)
class OptionTokenStream:
    """Stateful scanner for dynamic CLI option tokens."""

    tokens: list[str]
    index: int = 0

    @property
    def has_next(self) -> bool:
        """Whether another token is available."""
        return self.index < len(self.tokens)

    def next_argument(self) -> tuple[str, Any]:
        """Return the next parsed argument pair."""
        raw_argument = self.tokens[self.index]
        self._validate_option_token(raw_argument)
        if "=" in raw_argument:
            return self._argument_from_assignment(raw_argument)
        return self._argument_from_pair(raw_argument)

    def _argument_from_assignment(self, raw_argument: str) -> tuple[str, Any]:
        raw_key, raw_payload = raw_argument[2:].split("=", 1)
        self.index += 1
        return self._validate_argument_key(raw_key), self._parse_json_value(raw_payload)

    def _argument_from_pair(self, raw_argument: str) -> tuple[str, Any]:
        raw_key = raw_argument[2:]
        if self._next_token_is_payload():
            raw_payload = self.tokens[self.index + 1]
            self.index += 2
            return self._validate_argument_key(raw_key), self._parse_json_value(raw_payload)
        self.index += 1
        return self._validate_argument_key(raw_key), True

    def _next_token_is_payload(self) -> bool:
        next_index = self.index + 1
        if next_index >= len(self.tokens):
            return False
        return not self.tokens[next_index].startswith(OPTION_PREFIX)

    def _validate_option_token(self, raw_argument: str) -> None:
        if not raw_argument.startswith(OPTION_PREFIX) or raw_argument == OPTION_PREFIX:
            raise ToolArgumentsError(
                f"Tool arguments must use --name value syntax: {raw_argument}",
            )

    def _validate_argument_key(self, raw_key: str) -> str:
        if not ARGUMENT_KEY_PATTERN.fullmatch(raw_key):
            raise ToolArgumentsError(
                f"Invalid tool argument name: {raw_key}. "
                "Use a top-level JSON property name or --args-json.",
            )
        return raw_key

    def _parse_json_value(self, raw_payload: str) -> Any:
        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError:
            return raw_payload


def parse_tool_arguments(
    tokens: list[str],
    *,
    args_json: str | None = None,
    args_json_file: Path | None = None,
) -> dict[str, Any]:
    return ToolArgumentsParser().parse(tokens, args_json=args_json, args_json_file=args_json_file)


@dataclass(frozen=True, slots=True)
class SchemaArgumentNormalizer:
    """Map CLI-friendly argument names onto JSON schema property names."""

    def normalize(
        self,
        arguments: dict[str, Any],
        *,
        input_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return arguments with schema-backed camelCase aliases applied."""
        properties = self._schema_properties(input_schema)
        if not properties:
            return arguments
        aliases = self._property_aliases(properties)
        normalized_arguments: dict[str, Any] = {}
        for argument_key, argument_value in arguments.items():
            normalized_key = self._normalized_key(
                argument_key=argument_key,
                properties=properties,
                aliases=aliases,
            )
            if normalized_key in normalized_arguments:
                raise ToolArgumentsError(f"Duplicate tool argument: {normalized_key}")
            normalized_arguments[normalized_key] = argument_value
        return normalized_arguments

    def _schema_properties(self, input_schema: dict[str, Any] | None) -> dict[str, Any]:
        if input_schema is None:
            return {}
        properties = input_schema.get(PROPERTIES_KEY)
        if not isinstance(properties, dict):
            return {}
        return cast("dict[str, Any]", properties)

    def _property_aliases(self, properties: dict[str, Any]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        duplicate_signatures: set[str] = set()
        for property_name in properties:
            signature = self._argument_signature(property_name)
            if signature in aliases:
                duplicate_signatures.add(signature)
            else:
                aliases[signature] = property_name
        for duplicate_signature in duplicate_signatures:
            aliases.pop(duplicate_signature)
        return aliases

    def _normalized_key(
        self,
        *,
        argument_key: str,
        properties: dict[str, Any],
        aliases: dict[str, str],
    ) -> str:
        if argument_key in properties:
            return argument_key
        return aliases.get(self._argument_signature(argument_key), argument_key)

    def _argument_signature(self, argument_key: str) -> str:
        return argument_key.replace("_", "").replace("-", "").lower()


def normalize_tool_arguments(
    arguments: dict[str, Any],
    *,
    input_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    return SchemaArgumentNormalizer().normalize(arguments, input_schema=input_schema)
