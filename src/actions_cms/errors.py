"""Error types shared by the library and the CLI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class CmsError(Exception):
    """Base class for errors the CLI reports without a traceback."""


class ConfigError(CmsError):
    """cms.yaml, the site layout or the invocation is wrong (exit code 2)."""


@dataclass(frozen=True)
class Problem:
    """One thing wrong with one file."""

    path: Path | None
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class ContentError(CmsError, ValueError):
    """Content on disk breaks the contract (exit code 1)."""

    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("\n".join(map(str, problems)))
