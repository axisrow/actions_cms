"""Builders for throw-away sites. All content here is synthetic."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from actions_cms import config
from actions_cms.content import write_frontmatter

RUBRICS = {"news": "News", "guide": "Guides"}
MKDOCS = """\
site_name: Test site
docs_dir: docs
plugins:
  - search
  - blog:
      post_excerpt: required
"""
BODY = "\nLead paragraph.\n\n<!-- more -->\n\n## Section\n\nText.\n"


def make_site(root: Path, cms: dict | None = None, mkdocs: str | None = MKDOCS) -> config.Site:
    root.mkdir(parents=True, exist_ok=True)
    (root / "cms.yaml").write_text(yaml.safe_dump(cms or {"rubrics": RUBRICS}, allow_unicode=True), encoding="utf-8")
    if mkdocs is not None:
        (root / "mkdocs.yml").write_text(mkdocs, encoding="utf-8")
    (root / "drafts").mkdir(exist_ok=True)
    (root / "docs" / "blog" / "posts").mkdir(parents=True, exist_ok=True)
    return config.load(root)


def meta(**overrides) -> dict:
    """Valid front-matter; pass `field=None` to leave a field out."""
    base = {
        "title": "First post",
        "date": dt.date(2026, 1, 15),
        "rubric": "news",
        "summary": "Short summary.",
        "status": "draft",
    }
    return {k: v for k, v in {**base, **overrides}.items() if v is not None}


def draft(site: config.Site, name: str = "01-first-post.md", batch: str = "2026-01-15", body: str = BODY, **overrides) -> Path:
    path = site.drafts / batch / name
    path.parent.mkdir(parents=True, exist_ok=True)
    write_frontmatter(path, meta(**overrides), body)
    return path


def post(site: config.Site, name: str = "2026-01-10-old-post.md", **overrides) -> Path:
    path = site.posts / name
    write_frontmatter(path, meta(status="approved", **overrides), BODY)
    return path


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under root — to assert that a failed command changed nothing."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
