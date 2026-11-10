"""Collect new article links from the article sections of watched sites into `<inbox>/YYYY-MM-DD.json`.

Config (`collect.sites.config`, default config/sites.yaml) is a list of sites, or a mapping whose
list values are groups of sites. A site is collected if it has `articles` or `rss`:
    - name: Example
      articles: https://example.com/blog/     # section whose articles to watch
      rss: https://example.com/feed/          # optional, tried first
      keywords: [...]                         # optional: keep only titles with one of these words

Per site, sources are tried in order until one yields links:
  1. `rss`      — the site's own feed;
  2. `articles` — links found in the HTML of the section;
  3. sitemap    — URLs under the section path, from robots.txt `Sitemap:` or /sitemap.xml
                  (for sections that render their list with JavaScript).
A URL already present in any inbox file is never reported again.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import feedparser

from ..config import Site
from . import load_config, load_items, save_items

MAX_CHILD_SITEMAPS = 30
Link = tuple[str, str]  # (url, title)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[Link] = []
        self._href: str | None = None
        self._label = ""
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            self._href, self._label, self._text = a.get("href"), a.get("title") or a.get("aria-label") or "", []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.links.append((self._href, text if len(text) >= len(self._label) else self._label))
            self._href = None


def fetcher(user_agent: str, timeout: int = 30) -> Callable[[str], str]:
    def fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")
    return fetch


def slug_title(url: str) -> str:
    """Readable title from the last URL segment, for links without anchor text."""
    seg = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    return re.sub(r"\.(html?|php)$", "", seg).replace("-", " ").replace("_", " ").strip()


PAGINATION = re.compile(r"/(browse|page)/\d+(\.html?)?/?$|[?&]page=\d+")
TEASER_META = re.compile(r"^\d{1,2}[./]\d{1,2}[./]\d{4}\s+(\d+\s*min\s+)?", re.I)  # "10/22/2026 5min "


def clean(links: list[Link]) -> list[Link]:
    """Drop pagination links and letterless titles ("2"), strip date/read-time prefixes."""
    out = []
    for url, title in links:
        title = TEASER_META.sub("", title).strip()
        if PAGINATION.search(url) or not re.search(r"[^\W\d_]", title):
            continue
        out.append((url, title))
    return out


def in_section(url: str, section: str) -> bool:
    """URL is an article below the section: /useful/ → /useful/x.html, /tips.html → /tips/x.html."""
    u, s = urlparse(url), urlparse(section)
    base = re.sub(r"\.(html?|php)$", "", s.path).rstrip("/")
    return u.netloc == s.netloc and u.path.startswith(base + "/") and u.path.rstrip("/") != base


def from_rss(feed_url: str, user_agent: str, parse: Callable = feedparser.parse) -> list[Link]:
    parsed = parse(feed_url, agent=user_agent)
    return [(e.link, e.get("title", "").strip() or slug_title(e.link)) for e in parsed.entries if e.get("link")]


def from_html(section: str, fetch: Callable[[str], str]) -> list[Link]:
    parser = LinkParser()
    parser.feed(fetch(section))
    found: dict[str, str] = {}
    for href, text in parser.links:
        url = urljoin(section, href).split("#")[0]
        if in_section(url, section):
            title = text if len(text) >= 20 else found.get(url) or slug_title(url)
            if len(title) > len(found.get(url, "")):
                found[url] = title[:300]
    return list(found.items())


def sitemap_urls(section: str, fetch: Callable[[str], str]) -> list[str]:
    root = f"{urlparse(section).scheme}://{urlparse(section).netloc}"
    try:
        maps = re.findall(r"(?im)^sitemap:\s*(\S+)", fetch(f"{root}/robots.txt")) or [f"{root}/sitemap.xml"]
    except Exception:
        maps = [f"{root}/sitemap.xml"]
    urls, queue, seen = [], list(maps), set()
    while queue and len(seen) < MAX_CHILD_SITEMAPS:
        m = queue.pop(0)
        if m in seen:
            continue
        seen.add(m)
        try:
            tree = ET.fromstring(fetch(m).encode())
        except Exception:
            continue
        locs = [el.text.strip() for el in tree.iter() if el.tag.endswith("loc") and el.text]
        if tree.tag.endswith("sitemapindex"):
            queue += locs
        else:
            urls += locs
    return urls


def from_sitemap(section: str, fetch: Callable[[str], str]) -> list[Link]:
    return [(u, slug_title(u)) for u in dict.fromkeys(sitemap_urls(section, fetch)) if in_section(u, section)]


def collect_one(entry: dict, fetch: Callable[[str], str], user_agent: str, parse: Callable) -> tuple[str, list[Link]]:
    """(method that worked, links). Raises RuntimeError listing what was tried if nothing did."""
    sources = (
        ("rss", entry.get("rss"), lambda src: from_rss(src, user_agent, parse)),
        ("html", entry.get("articles"), lambda src: from_html(src, fetch)),
        ("sitemap", entry.get("articles"), lambda src: from_sitemap(src, fetch)),
    )
    tried = []
    for method, src, read in sources:
        if not src:
            continue
        try:
            links = read(src)
        except Exception as e:  # one dead source must not stop the rest
            tried.append(f"{method}: {e}")
            continue
        if links:
            return method, links
        tried.append(f"{method}: 0")
    raise RuntimeError("; ".join(tried) or "no source configured")


def entries(cfg: object) -> list[dict]:
    """Sites to collect: a top-level list, or every list found among the values of a mapping."""
    if isinstance(cfg, list):
        groups = [cfg]
    elif isinstance(cfg, dict):
        groups = [value for value in cfg.values() if isinstance(value, list)]
    else:
        groups = []
    return [e for group in groups for e in group if isinstance(e, dict) and (e.get("articles") or e.get("rss"))]


def collect(
    site: Site,
    *,
    fetch: Callable[[str], str] | None = None,
    parse: Callable = feedparser.parse,
    now: datetime | None = None,
) -> Path | None:
    """Append links not seen before to today's inbox file. Returns it, or None if there is nothing to write."""
    watched = entries(load_config(site.sites.config))
    fetch = fetch or fetcher(site.sites.user_agent)
    inbox = site.sites.inbox
    seen = {i["url"] for f in sorted(inbox.glob("*.json")) for i in load_items(f)}
    out = inbox / f"{now or datetime.now(timezone.utc):%Y-%m-%d}.json"
    items = load_items(out)
    total = 0

    for entry in watched:
        name = entry.get("name") or urlparse(entry.get("articles") or entry["rss"]).netloc
        try:
            method, links = collect_one(entry, fetch, site.sites.user_agent, parse)
        except Exception as e:
            print(f"! {name}: {e}")
            continue
        keywords = [str(k).lower() for k in entry.get("keywords") or []]
        links = clean(links)
        relevant = [(u, t) for u, t in links if not keywords or any(k in t.lower() for k in keywords)]
        added = 0
        for url, title in relevant:
            if url in seen:
                continue
            items.append({"source": name, "title": title, "url": url})
            seen.add(url)
            added += 1
        total += added
        print(f"{name} [{method}]: {len(links)} links, {len(relevant)} relevant, +{added} new")

    if not total:
        print(f"{site.show(inbox)}: nothing new")
        return None
    save_items(out, items)
    print(f"{site.show(out)}: {len(items)} items")
    return out
