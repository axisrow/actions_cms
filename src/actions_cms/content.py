"""Articles on disk: front-matter, slugs and the article index.

`read_frontmatter`, `write_frontmatter` and `slug_of` are a stable API — site-side scripts import them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .errors import ContentError, Problem

_OPEN = re.compile(r"\A---[ \t]*\r?\n")
_CLOSE = re.compile(r"^---[ \t]*$", re.M)
_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{2})-")
_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def read_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (meta, body). The body keeps everything after the closing `---`, newline included."""
    text = path.read_text(encoding="utf-8")
    opened = _OPEN.match(text)
    # Delimiters are whole lines, so a `---` inside a value does not cut the block short.
    closed = _CLOSE.search(text, opened.end()) if opened else None
    if not closed:
        raise ContentError([Problem(path, "no front-matter")])
    try:
        meta = yaml.safe_load(text[opened.end():closed.start()]) or {}
    except yaml.YAMLError as e:
        raise ContentError([Problem(path, f"invalid front-matter: {' '.join(str(e).split())}")]) from e
    if not isinstance(meta, dict):
        raise ContentError([Problem(path, "front-matter must be a mapping")])
    return meta, text[closed.start() + 3:]


def write_frontmatter(path: Path, meta: dict, body: str) -> None:
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{fm}---{body}", encoding="utf-8")


def slug_of(path: Path) -> str:
    """Strip the `NN-` (drafts) or `YYYY-MM-DD-` (posts) prefix from a file stem."""
    slug = _PREFIX.sub("", path.stem)
    if not _SLUG.fullmatch(slug):
        raise ContentError([Problem(path, f"slug '{slug}' is not latin — name the file NN-latin-slug.md")])
    return slug


def load_index(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_index(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
