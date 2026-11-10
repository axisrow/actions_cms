"""Collect fresh items from RSS/Atom feeds into `<inbox>/YYYY-MM-DD.json`.

Config (`collect.feeds.config`, default config/sources.yaml):
    keywords: [...]   # for feeds with `filter: true`: keep items mentioning one of these
    exclude:  [...]   # drop items mentioning one of these, in every feed
    feeds:
      - {name: ..., url: ..., filter: true}
"""
from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import feedparser

from ..config import Site
from ..errors import ConfigError
from . import load_config, load_items, save_items


def clean(html: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()[:limit]


def entry_ts(entry) -> float | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return calendar.timegm(parsed) if parsed else None


def collect(
    site: Site,
    hours: int | None = None,
    *,
    parse: Callable = feedparser.parse,
    now: datetime | None = None,
) -> Path | None:
    """Append new feed items to today's inbox file. Returns it, or None if there is nothing to write."""
    cfg = load_config(site.feeds.config) or {}
    if not isinstance(cfg, dict):
        raise ConfigError(f"{site.feeds.config}: must be a mapping with `feeds`")
    feeds = cfg.get("feeds") or []
    if not all(isinstance(f, dict) and f.get("name") and f.get("url") for f in feeds):
        raise ConfigError(f"{site.feeds.config}: every feed needs `name` and `url`")
    keywords = [str(k).lower() for k in cfg.get("keywords") or []]
    exclude = [str(k).lower() for k in cfg.get("exclude") or []]

    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - (hours or site.feeds.hours) * 3600
    out = site.feeds.inbox / f"{now:%Y-%m-%d}.json"
    items = load_items(out)
    seen = {i["url"] for i in items}
    total = 0

    for feed in feeds:
        try:
            agent = site.feeds.user_agent
            parsed = parse(feed["url"], agent=agent) if agent else parse(feed["url"])
        except Exception as e:  # one dead feed must not stop the rest
            print(f"! {feed['name']}: {e}")
            continue
        if parsed.bozo and not parsed.entries:
            print(f"! {feed['name']}: {parsed.bozo_exception}")
            continue
        added = 0
        for e in parsed.entries:
            url, ts = e.get("link"), entry_ts(e)
            if not url or url in seen or (ts and ts < cutoff):
                continue
            title, summary = clean(e.get("title", ""), 300), clean(e.get("summary", ""))
            text = f"{title} {summary}".lower()
            if feed.get("filter") and keywords and not any(k in text for k in keywords):
                continue
            if any(k in text for k in exclude):
                continue
            items.append({
                "title": title,
                "url": url,
                "source": feed["name"],
                "published": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                "summary": summary,
            })
            seen.add(url)
            added += 1
        total += added
        print(f"{feed['name']}: +{added}")

    if not total:
        print(f"{site.show(site.feeds.inbox)}: nothing new")
        return None
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    save_items(out, items)
    print(f"{site.show(out)}: {len(items)} items")
    return out
