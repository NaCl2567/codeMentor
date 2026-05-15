from __future__ import annotations

from typing import Any


class SafeFormatDict(dict[str, Any]):
    """Keep unknown prompt placeholders visible instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def safe_format_prompt(template: str, **values: Any) -> str:
    return template.format_map(SafeFormatDict(values))
