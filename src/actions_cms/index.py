"""The article index: one JSON registry of every post and draft, rebuilt from the files."""
from __future__ import annotations

from pathlib import Path

from .config import Site
from .content import load_index, read_frontmatter, save_index, slug_of
from .errors import ContentError, Problem


def article_files(site: Site) -> list[Path]:
    return sorted(site.posts.glob("*.md")) + sorted(site.drafts.glob("*/*.md"))


def build(site: Site) -> list[dict]:
    """Index entries for every article on disk. All or nothing: any bad file raises ContentError."""
    entries: dict[str, dict] = {}
    owners: dict[str, Path] = {}
    problems: list[Problem] = []
    for path in article_files(site):
        try:
            meta, _ = read_frontmatter(path)
            slug = slug_of(path)
        except ContentError as e:
            problems += e.problems
            continue
        missing = [k for k in site.required if not meta.get(k)]
        if missing:
            problems.append(Problem(path, f"missing {', '.join(missing)}"))
            continue
        if slug in owners:
            problems.append(Problem(path, f"slug '{slug}' is already used by {site.show(owners[slug])}"))
            continue
        owners[slug] = path
        entries[slug] = {
            "slug": slug,
            "title": meta["title"],
            "date": str(meta["date"]),
            "rubric": meta["rubric"],
            "tags": meta.get("tags") or [],
            "status": meta["status"],
            "path": site.rel(path),
        }
    if problems:
        raise ContentError(problems)
    return sorted(entries.values(), key=lambda i: (i["date"], i["path"]))


def sync(site: Site) -> tuple[list[str], list[str]]:
    """Rewrite the index from the files. Returns the slugs that appeared and those that went away."""
    old = load_index(site.index)
    new = build(site)
    if new != old or not site.index.exists():
        save_index(site.index, new)
    before, after = {i["slug"] for i in old}, {i["slug"] for i in new}
    return sorted(after - before), sorted(before - after)
