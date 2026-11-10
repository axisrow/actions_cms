"""Turn drafts into published posts: plan and check everything first, then move."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from . import generators, index
from .config import Site
from .content import read_frontmatter, slug_of, write_frontmatter
from .errors import ContentError, Problem


@dataclass(frozen=True)
class Move:
    draft: Path
    target: Path
    meta: dict
    body: str


def _published_slugs(site: Site) -> dict[str, Path]:
    slugs = {}
    for post in sorted(site.posts.glob("*.md")):
        try:
            slugs.setdefault(slug_of(post), post)
        except ContentError:
            pass  # a hand-named page in the posts folder cannot collide with a draft slug
    return slugs


def plan(site: Site, approve_all: bool = False) -> tuple[list[Move], list[Problem]]:
    """Moves for the selected drafts and every problem found in them. Touches nothing.

    With `approve_all` every draft is selected (a merged PR is the approval);
    otherwise only drafts already marked `status: approved`.
    """
    gen = generators.get(site.generator)
    gen_settings = gen.settings(site)
    published = _published_slugs(site)
    claimed: dict[str, Path] = {}
    moves: list[Move] = []
    problems: list[Problem] = []

    for draft in sorted(site.drafts.glob("*/*.md")):
        try:
            meta, body = read_frontmatter(draft)
        except ContentError as e:
            problems += e.problems
            continue
        if not approve_all and meta.get("status") != "approved":
            continue

        errors: list[str] = []
        slug = None
        try:
            slug = slug_of(draft)
        except ContentError as e:
            errors.append(e.problems[0].message)
        if slug and meta.get("slug") not in (None, slug):
            errors.append(f"front-matter slug '{meta['slug']}' differs from the file name — remove it")

        missing = [k for k in site.required if not meta.get(k)]
        if missing:
            errors.append(f"missing {', '.join(missing)}")
        rubric = meta.get("rubric")
        if rubric and rubric not in site.rubrics:
            errors.append(f"unknown rubric '{rubric}' (cms.yaml has: {', '.join(site.rubrics)})")
        summary = meta.get("summary")
        if site.summary_max and isinstance(summary, str) and len(summary) > site.summary_max:
            errors.append(f"summary is {len(summary)} characters, the limit is {site.summary_max}")
        tags = meta.get("tags")
        if tags is not None and not isinstance(tags, list):
            errors.append("tags must be a list")
        date = meta.get("date")
        day = date.date() if isinstance(date, dt.datetime) else date if isinstance(date, dt.date) else None
        if date and not day:  # a quoted date is a string: no file name can be built from it
            errors.append("date must be an unquoted YAML date: YYYY-MM-DD")
        errors += gen.check_post(site, gen_settings, meta, body)

        target = site.posts / gen.post_filename(day, slug) if slug and day else None
        if slug:
            if slug in claimed:
                errors.append(f"slug '{slug}' is also used by {site.show(claimed[slug])}")
            claimed.setdefault(slug, draft)
            if slug in published:
                errors.append(f"slug '{slug}' is already published: {site.show(published[slug])}")
            elif target and target.exists():
                errors.append(f"{site.show(target)} already exists")

        if errors:
            problems += [Problem(draft, message) for message in errors]
            continue
        if approve_all:
            meta = {**meta, "status": "approved"}
        moves.append(Move(draft, target, gen.prepare_post(site, meta, slug), body))

    # Publishing ends with an index rebuild over every article, so anything that would break it —
    # a malformed post already on the site, a draft left out of this run — has to surface now.
    flagged = {problem.path for problem in problems}
    try:
        index.build(site)
    except ContentError as e:
        problems += [problem for problem in e.problems if problem.path not in flagged]

    return moves, problems


def promote(site: Site, approve_all: bool = False) -> list[Move]:
    """Move the selected drafts into the posts folder and rebuild the index.

    Raises ContentError before moving anything if any selected draft has a problem.
    """
    moves, problems = plan(site, approve_all)
    if problems:
        raise ContentError(problems)
    site.posts.mkdir(parents=True, exist_ok=True)
    for move in moves:
        write_frontmatter(move.target, move.meta, move.body)
        move.draft.unlink()
        batch = move.draft.parent
        if batch != site.drafts and not any(batch.iterdir()):
            batch.rmdir()
    if moves:
        index.sync(site)
    return moves
