"""`cms init`: unpack the site template that ships inside the package.

Template conventions:
  * `__TOKEN__` placeholders are replaced in file contents and in path names
    (never `${{ }}`, so workflow expressions pass through untouched);
  * a file named `name.<lang>.ext` is a language variant: only the one for the chosen
    language is written, as `name.ext`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import ENGINE_REPO, __version__, config, index
from .errors import ConfigError

TEMPLATE = Path(__file__).resolve().parent / "template"

# Interface labels that end up in YAML; prose lives in the language-variant files.
LANGS = {
    "ru": {
        "NAV_HOME": "Главная", "NAV_BLOG": "Статьи",
        "TO_DARK": "Тёмная тема", "TO_LIGHT": "Светлая тема",
        "CAT_NEWS": "Новости", "CAT_GUIDE": "Гайды",
    },
    "en": {
        "NAV_HOME": "Home", "NAV_BLOG": "Blog",
        "TO_DARK": "Switch to dark mode", "TO_LIGHT": "Switch to light mode",
        "CAT_NEWS": "News", "CAT_GUIDE": "Guides",
    },
}
_VARIANT = re.compile(rf"^(?P<stem>.+)\.(?P<lang>{'|'.join(LANGS)})(?P<ext>\.[^.]+)$")
_TOKEN = re.compile(r"__([A-Z][A-Z0-9_]*?)__")
_REPO = re.compile(r"[\w.-]+/[\w.-]+")


def default_engine_ref() -> str:
    return f"v{__version__.split('.')[0]}"


def pages_url(repo: str) -> str:
    owner, name = repo.split("/")
    return f"https://{owner}.github.io/" if name.lower() == f"{owner}.github.io".lower() else f"https://{owner}.github.io/{name}/"


def _render(text: str, tokens: dict[str, str], where: str, yaml_escape: bool = False) -> str:
    def replace(match: re.Match) -> str:
        try:
            value = tokens[match.group(1)]
        except KeyError:
            raise ConfigError(f"template bug: unknown token {match.group(0)} in {where}") from None
        # Inside a double-quoted YAML scalar a JSON string body is a valid escape of any text.
        return json.dumps(value, ensure_ascii=False)[1:-1] if yaml_escape else value
    return _TOKEN.sub(replace, text)


def init(
    target: Path,
    *,
    name: str,
    repo: str,
    description: str = "",
    site_url: str | None = None,
    lang: str = "ru",
    engine_ref: str | None = None,
    force: bool = False,
    today: dt.date | None = None,
) -> tuple[list[str], list[str]]:
    """Create a site in `target`. Returns (written, skipped) relative paths.

    Existing files are left alone unless `force`.
    """
    if lang not in LANGS:
        raise ConfigError(f"unknown language '{lang}' (available: {', '.join(LANGS)})")
    if not _REPO.fullmatch(repo):
        raise ConfigError(f"--repo must look like owner/name, got '{repo}'")
    site_url = site_url or pages_url(repo)
    tokens = {
        **LANGS[lang],
        "SITE_NAME": name,
        "SITE_DESCRIPTION": description,
        "SITE_URL": site_url if site_url.endswith("/") else site_url + "/",
        "REPO": repo,
        "REPO_URL": f"https://github.com/{repo}",
        "LANG": lang,
        "ENGINE_REPO": ENGINE_REPO,
        "ENGINE_REF": engine_ref or default_engine_ref(),
        "TODAY": (today or dt.date.today()).isoformat(),
    }

    written, skipped = [], []
    for source in sorted(p for p in TEMPLATE.rglob("*") if p.is_file()):
        rel = source.relative_to(TEMPLATE)
        variant = _VARIANT.match(rel.name)
        if variant:
            if variant["lang"] != lang:
                continue
            rel = rel.with_name(variant["stem"] + variant["ext"])
        rel = Path(_render(rel.as_posix(), tokens, str(rel)))
        dest = target / rel
        if dest.exists() and not force:
            skipped.append(rel.as_posix())
            continue
        text = _render(source.read_text(encoding="utf-8"), tokens, str(rel), rel.suffix in (".yml", ".yaml"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written.append(rel.as_posix())

    index.sync(config.load(target))  # register the sample draft
    return written, skipped
