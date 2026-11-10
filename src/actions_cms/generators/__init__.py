"""Static-site generators. Everything a generator dictates lives in its module, nowhere else.

A generator module provides:
    settings(site)                         -> what its own config says about posts
    post_filename(day, slug)               -> file name of a published post
    prepare_post(site, meta, slug)         -> front-matter of the published post
    check_post(site, settings, meta, body) -> list[str] of problems with one draft
    check_site(site)                       -> list[Problem] with the site configuration
    build(site, capture=False)             -> CompletedProcess of a strict build
    output_dir(site)                       -> where the built site lands
"""
from __future__ import annotations

from types import ModuleType

from ..errors import ConfigError
from . import mkdocs_material

_GENERATORS = {mkdocs_material.NAME: mkdocs_material}


def get(name: str) -> ModuleType:
    try:
        return _GENERATORS[name]
    except KeyError:
        raise ConfigError(f"unknown generator '{name}' (available: {', '.join(_GENERATORS)})") from None
