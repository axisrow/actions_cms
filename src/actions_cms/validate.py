"""Check a site before its drafts are merged: static checks, optionally a trial publish and build."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import config, generators, promote
from .config import Site
from .errors import ContentError, Problem

# Never needed for a build, and potentially large.
_SKIP_NAMES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache", ".pytest_cache"}


def static(site: Site) -> list[Problem]:
    """Problems with the site configuration and with every draft (as if all were approved)."""
    _, problems = promote.plan(site, approve_all=True)
    return generators.get(site.generator).check_site(site) + problems


def _copy(site: Site, target: Path) -> None:
    gen = generators.get(site.generator)
    skip_paths = {gen.output_dir(site).resolve(), site.feeds.inbox, site.sites.inbox}

    def ignore(folder: str, names: list[str]) -> list[str]:
        return [n for n in names if n in _SKIP_NAMES or (Path(folder) / n).resolve() in skip_paths]

    shutil.copytree(site.root, target, ignore=ignore, symlinks=True)


def preview_build(site: Site) -> tuple[bool, str]:
    """Publish every draft into a throw-away copy of the site and build it strictly.

    Returns (ok, build output). The real site is not touched. Generator plugins that read
    git history see no repository in the copy.
    """
    gen = generators.get(site.generator)
    with tempfile.TemporaryDirectory(prefix="cms-preview-") as tmp:
        copy_root = Path(tmp).resolve() / "site"
        _copy(site, copy_root)
        copy = config.load(copy_root)
        try:
            promote.promote(copy, approve_all=True)
        except ContentError as e:  # static() normally reports these first
            return False, "\n".join(str(p) for p in e.problems).replace(str(copy_root), str(site.root))
        result = gen.build(copy, capture=True)
        return result.returncode == 0, (result.stdout or "").replace(str(copy_root), str(site.root))
