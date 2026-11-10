"""Site settings: `cms.yaml` in the site root, with defaults for everything but the rubrics."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import ConfigError

CONFIG_NAME = "cms.yaml"
# Fields every article must carry; `required` in cms.yaml adds to these.
CORE_REQUIRED = ("title", "date", "rubric", "status")
DEFAULT_SITES_UA = "Mozilla/5.0 (compatible; actions-cms-bot/1.0)"


@dataclass(frozen=True)
class Feeds:
    config: Path
    inbox: Path
    hours: int
    user_agent: str | None  # None = feedparser's own User-Agent


@dataclass(frozen=True)
class Sites:
    config: Path
    inbox: Path
    user_agent: str


@dataclass(frozen=True)
class Site:
    root: Path
    generator: str
    drafts: Path
    posts: Path
    index: Path
    rubrics: dict[str, str | None]  # rubric -> category label on the site (None = no category)
    required: tuple[str, ...]
    summary_max: int  # 0 = no limit
    feeds: Feeds
    sites: Sites

    def rel(self, path: Path) -> str:
        """Path relative to the site root with forward slashes — the form stored in the index."""
        return path.resolve().relative_to(self.root).as_posix()

    def show(self, path: Path) -> str:
        """Like `rel`, but never fails: for messages."""
        try:
            return self.rel(path)
        except ValueError:
            return str(path)


def find_root(start: Path) -> Path:
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / CONFIG_NAME).is_file():
            return folder
    raise ConfigError(f"{CONFIG_NAME} not found in {start} or above — run `cms init` or pass --root")


def _mapping(data: dict, key: str, allowed: tuple[str, ...], where: str = "") -> dict:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{CONFIG_NAME}: {where}{key} must be a mapping")
    unknown = sorted(set(map(str, value)) - set(allowed))
    if unknown:
        raise ConfigError(f"{CONFIG_NAME}: unknown key in {where}{key}: {', '.join(unknown)}")
    return value


def _path(root: Path, value: object, key: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{CONFIG_NAME}: {key} must be a path")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ConfigError(f"{CONFIG_NAME}: {key} points outside the site: {value}")
    return path


def _int(value: object, key: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"{CONFIG_NAME}: {key} must be an integer >= {minimum}")
    return value


def _user_agent(value: object, key: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ConfigError(f"{CONFIG_NAME}: {key} must be a non-empty string")
    return value


def load(root: Path | str | None = None) -> Site:
    """Load the site whose root is `root`, or the nearest one above the current directory."""
    if root is None:
        root = find_root(Path.cwd())
    else:
        root = Path(root).resolve()
        if not (root / CONFIG_NAME).is_file():
            raise ConfigError(f"{root}: no {CONFIG_NAME} here")
    try:
        data = yaml.safe_load((root / CONFIG_NAME).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{CONFIG_NAME}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{CONFIG_NAME}: must be a mapping")
    unknown = sorted(set(map(str, data)) - {"generator", "paths", "rubrics", "required", "summary_max", "collect"})
    if unknown:
        raise ConfigError(f"{CONFIG_NAME}: unknown key: {', '.join(unknown)}")

    rubrics = data.get("rubrics")
    if not isinstance(rubrics, dict) or not rubrics:
        raise ConfigError(f"{CONFIG_NAME}: rubrics is required — a mapping of rubric to category label")
    for rubric, label in rubrics.items():
        if not isinstance(rubric, str) or not (label is None or isinstance(label, str)):
            raise ConfigError(f"{CONFIG_NAME}: rubrics must map names to category labels (or null): {rubric!r}")

    extra = data.get("required", ["summary"])
    if not isinstance(extra, list) or not all(isinstance(k, str) for k in extra):
        raise ConfigError(f"{CONFIG_NAME}: required must be a list of front-matter fields")

    paths = _mapping(data, "paths", ("drafts", "posts", "index"))
    collect = _mapping(data, "collect", ("feeds", "sites"))
    feeds = _mapping(collect, "feeds", ("config", "inbox", "hours", "user_agent"), "collect.")
    sites = _mapping(collect, "sites", ("config", "inbox", "user_agent"), "collect.")

    return Site(
        root=root,
        generator=str(data.get("generator", "mkdocs-material")),
        drafts=_path(root, paths.get("drafts", "drafts"), "paths.drafts"),
        posts=_path(root, paths.get("posts", "docs/blog/posts"), "paths.posts"),
        index=_path(root, paths.get("index", "content/index.json"), "paths.index"),
        rubrics=dict(rubrics),
        required=tuple(dict.fromkeys((*CORE_REQUIRED, *extra))),
        summary_max=_int(data.get("summary_max", 280), "summary_max", 0),
        feeds=Feeds(
            config=_path(root, feeds.get("config", "config/sources.yaml"), "collect.feeds.config"),
            inbox=_path(root, feeds.get("inbox", "inbox/news"), "collect.feeds.inbox"),
            hours=_int(feeds.get("hours", 48), "collect.feeds.hours", 1),
            user_agent=_user_agent(feeds.get("user_agent"), "collect.feeds.user_agent"),
        ),
        sites=Sites(
            config=_path(root, sites.get("config", "config/sites.yaml"), "collect.sites.config"),
            inbox=_path(root, sites.get("inbox", "inbox/sites"), "collect.sites.inbox"),
            user_agent=_user_agent(sites.get("user_agent"), "collect.sites.user_agent") or DEFAULT_SITES_UA,
        ),
    )
