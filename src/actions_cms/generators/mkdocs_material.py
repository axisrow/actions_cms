"""MkDocs Material with its built-in blog plugin."""
from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..config import CONFIG_NAME, Site
from ..errors import ConfigError, Problem

NAME = "mkdocs-material"
CONFIG = "mkdocs.yml"


class _TolerantLoader(yaml.SafeLoader):
    """Reads mkdocs.yml without executing it: `!ENV`, `!!python/name:...` and friends become None."""


_TolerantLoader.add_multi_constructor("", lambda loader, suffix, node: None)


@dataclass(frozen=True)
class Blog:
    enabled: bool
    posts: Path  # where the blog plugin looks for posts
    excerpt_required: bool
    separator: str
    categories_allowed: tuple[str, ...]


def _config(site: Site) -> dict:
    path = site.root / CONFIG
    if not path.is_file():
        return {}
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_TolerantLoader)  # noqa: S506 — safe subclass
    except yaml.YAMLError as e:
        raise ConfigError(f"{CONFIG}: invalid YAML: {' '.join(str(e).split())}") from e
    return data if isinstance(data, dict) else {}


def _plugin(config: dict, name: str) -> dict | None:
    """Options of a plugin, {} if enabled without options, None if absent."""
    plugins = config.get("plugins")
    if plugins is None:
        return None
    items = plugins.items() if isinstance(plugins, dict) else (
        next(iter(p.items())) if isinstance(p, dict) and p else (p, None) for p in plugins
    )
    for key, options in items:
        if key in (name, f"material/{name}"):
            return options if isinstance(options, dict) else {}
    return None


def settings(site: Site) -> Blog:
    config = _config(site)
    blog = _plugin(config, "blog")
    options = blog or {}
    blog_dir = str(options.get("blog_dir", "blog"))
    post_dir = str(options.get("post_dir", "{blog}/posts")).format(blog=blog_dir)
    return Blog(
        enabled=blog is not None,
        posts=(site.root / str(config.get("docs_dir", "docs")) / post_dir).resolve(),
        excerpt_required=options.get("post_excerpt", "optional") == "required",
        separator=str(options.get("post_excerpt_separator", "<!-- more -->")),
        categories_allowed=tuple(map(str, options.get("categories_allowed") or ())),
    )


def output_dir(site: Site) -> Path:
    return site.root / str(_config(site).get("site_dir", "site"))


def post_filename(day: dt.date, slug: str) -> str:
    return f"{day.isoformat()}-{slug}.md"


def _allowed(site: Site, blog: Blog) -> set[str]:
    return set(blog.categories_allowed) or {label for label in site.rubrics.values() if label}


def prepare_post(site: Site, meta: dict, slug: str) -> dict:
    """Front-matter of the published post: `categories` from the rubric if absent, `slug` for a latin URL."""
    label = site.rubrics.get(meta.get("rubric"))
    fill = bool(label) and not meta.get("categories")
    post: dict = {}
    for key, value in meta.items():
        if key == "categories" and fill:
            continue
        post[key] = value
        if key == "rubric" and fill:
            post["categories"] = [label]
    post["slug"] = slug  # without it the blog plugin slugifies the title
    return post


def check_post(site: Site, blog: Blog, meta: dict, body: str) -> list[str]:
    errors = []
    if blog.excerpt_required and blog.separator not in body:
        errors.append(f"no excerpt separator {blog.separator} after the lead")
    categories = meta.get("categories")
    if categories:
        if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
            errors.append("categories must be a list of strings")
        else:
            foreign = [c for c in categories if c not in _allowed(site, blog)]
            if foreign:
                errors.append(f"categories not allowed on this site: {', '.join(foreign)}")
            label = site.rubrics.get(meta.get("rubric"))
            if label and label not in categories:
                errors.append(f"categories must include '{label}' (rubric {meta['rubric']})")
    return errors


def check_site(site: Site) -> list[Problem]:
    config_path = site.root / CONFIG
    if not config_path.is_file():
        return [Problem(config_path, "not found — the site has nothing to build")]
    blog = settings(site)
    if not blog.enabled:
        return [Problem(config_path, "the blog plugin is not enabled")]
    problems = []
    if blog.posts != site.posts:
        problems.append(Problem(
            site.root / CONFIG_NAME,
            f"paths.posts is {site.show(site.posts)}, but {CONFIG} renders posts from {site.show(blog.posts)}",
        ))
    if blog.categories_allowed:
        missing = [label for label in site.rubrics.values() if label and label not in blog.categories_allowed]
        if missing:
            problems.append(Problem(config_path, f"categories_allowed lacks rubric categories: {', '.join(missing)}"))
    return problems


def build(site: Site, capture: bool = False) -> subprocess.CompletedProcess:
    """`mkdocs build --strict` in the site root."""
    if importlib.util.find_spec("mkdocs") is None:
        raise ConfigError("mkdocs is not installed — pip install -r requirements.txt")
    return subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=site.root,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
