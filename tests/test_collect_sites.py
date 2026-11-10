import json
from datetime import datetime, timezone

import feedparser
import pytest
import yaml

from actions_cms.collect import sites
from helpers import make_site

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

BLOG_HTML = """
<html><body>
  <a href="/blog/how-to-pick-a-widget.html">How to pick a widget for the workshop</a>
  <a href="/blog/gadget-maintenance/">Read</a>
  <a href="/blog/gadget-maintenance/" title="Gadget maintenance in ten steps"><img src="x.png"></a>
  <a href="/blog/page/2/">2</a>
  <a href="/blog/">All articles in the blog section</a>
  <a href="/about/">About the company and its history</a>
  <a href="https://other.example/blog/elsewhere.html">An article on another site entirely</a>
</body></html>
"""
SITEMAP_INDEX = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://js.example/sitemap-posts.xml</loc></sitemap></sitemapindex>'
SITEMAP_POSTS = (
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://js.example/tips/first-tip.html</loc></url>"
    "<url><loc>https://js.example/tips/second_tip.html</loc></url>"
    "<url><loc>https://js.example/products/thing.html</loc></url>"
    "</urlset>"
)
PAGES = {
    "https://html.example/blog/": BLOG_HTML,
    "https://js.example/tips.html": "<html><body><div id='app'></div></body></html>",  # list rendered by a script
    "https://js.example/robots.txt": "User-agent: *\nSitemap: https://js.example/sitemap.xml\n",
    "https://js.example/sitemap.xml": SITEMAP_INDEX,
    "https://js.example/sitemap-posts.xml": SITEMAP_POSTS,
}
FEED = (
    '<?xml version="1.0"?><rss version="2.0"><channel><title>F</title>'
    "<item><title>Widget release notes</title><link>https://rss.example/news/release</link></item>"
    "<item><title>Racing team wins</title><link>https://rss.example/news/racing</link></item>"
    "</channel></rss>"
)


def fetch(url: str) -> str:
    if url not in PAGES:
        raise OSError(f"HTTP 404: {url}")
    return PAGES[url]


def parse(url, **kwargs):
    assert kwargs == {"agent": "test-bot/1.0"}
    return feedparser.parse(FEED if url == "https://rss.example/feed/" else "")


@pytest.fixture
def site(tmp_path):
    site = make_site(tmp_path, cms={
        "rubrics": {"news": "News"},
        "collect": {"sites": {"user_agent": "test-bot/1.0"}},
    })
    site.sites.config.parent.mkdir()
    return site


def configure(site, data):
    site.sites.config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def collected(site, **kwargs):
    out = sites.collect(site, fetch=fetch, parse=parse, now=NOW, **kwargs)
    return json.loads(out.read_text(encoding="utf-8")) if out else None


def test_entries_accepts_a_list_or_groups():
    a, b, c = {"name": "A", "articles": "https://a.example/blog/"}, {"name": "B", "rss": "https://b.example/feed"}, {"name": "C", "site": "https://c.example/"}
    assert sites.entries([a, b, c]) == [a, b]
    grouped = {"own": {"name": "Us", "site": "https://us.example/"}, "local": [a, c], "global": [b], "note": "text"}
    assert sites.entries(grouped) == [a, b]  # mappings and scalars are not groups; entries without a source are skipped
    assert sites.entries(None) == []


def test_links_come_from_the_section_html(site):
    configure(site, [{"name": "Html", "articles": "https://html.example/blog/"}])
    assert collected(site) == [
        {"source": "Html", "title": "How to pick a widget for the workshop", "url": "https://html.example/blog/how-to-pick-a-widget.html"},
        # the longest label wins over a bare "Read"; pagination, the section itself and foreign links are dropped
        {"source": "Html", "title": "Gadget maintenance in ten steps", "url": "https://html.example/blog/gadget-maintenance/"},
    ]


def test_the_sitemap_is_used_when_the_html_has_no_links(site, capsys):
    configure(site, [{"name": "Js", "articles": "https://js.example/tips.html"}])
    assert collected(site) == [
        {"source": "Js", "title": "first tip", "url": "https://js.example/tips/first-tip.html"},
        {"source": "Js", "title": "second tip", "url": "https://js.example/tips/second_tip.html"},
    ]
    assert "Js [sitemap]" in capsys.readouterr().out


def test_rss_is_tried_first_and_keywords_filter_titles(site, capsys):
    configure(site, {"partners": [{
        "name": "Rss", "rss": "https://rss.example/feed/", "articles": "https://html.example/blog/", "keywords": ["Widget"],
    }]})
    assert collected(site) == [{"source": "Rss", "title": "Widget release notes", "url": "https://rss.example/news/release"}]
    assert "Rss [rss]: 2 links, 1 relevant, +1 new" in capsys.readouterr().out


def test_a_url_seen_in_any_earlier_file_is_not_reported_again(site):
    configure(site, [{"name": "Html", "articles": "https://html.example/blog/"}])
    site.sites.inbox.mkdir(parents=True)
    # an older file, written before the item key was renamed from `competitor` to `source`
    (site.sites.inbox / "2026-01-10.json").write_text(json.dumps([
        {"competitor": "Html", "title": "Old", "url": "https://html.example/blog/how-to-pick-a-widget.html"},
    ]), encoding="utf-8")
    assert [i["url"] for i in collected(site)] == ["https://html.example/blog/gadget-maintenance/"]
    assert sites.collect(site, fetch=fetch, parse=parse, now=NOW) is None  # and nothing on the next run


def test_a_dead_site_does_not_stop_the_others(site, capsys):
    configure(site, [
        {"name": "Dead", "articles": "https://dead.example/blog/"},
        {"name": "Html", "articles": "https://html.example/blog/"},
    ])
    assert len(collected(site)) == 2
    assert "! Dead: html: HTTP 404" in capsys.readouterr().out


def test_no_file_is_created_when_there_is_nothing(site):
    configure(site, [])
    assert sites.collect(site, fetch=fetch, parse=parse, now=NOW) is None
    assert not site.sites.inbox.exists()


@pytest.mark.parametrize("url, section, expected", [
    ("https://x.example/useful/a.html", "https://x.example/useful/", True),
    ("https://x.example/tips/a.html", "https://x.example/tips.html", True),
    ("https://x.example/useful/", "https://x.example/useful/", False),
    ("https://x.example/other/a.html", "https://x.example/useful/", False),
    ("https://y.example/useful/a.html", "https://x.example/useful/", False),
])
def test_in_section(url, section, expected):
    assert sites.in_section(url, section) is expected


def test_clean_drops_pagination_and_strips_teaser_dates():
    assert sites.clean([
        ("https://x.example/blog/a", "10/22/2026 5min Useful article"),
        ("https://x.example/blog/page/3/", "Older posts"),
        ("https://x.example/blog/b", "2"),
        ("https://x.example/blog?page=2", "Next"),
    ]) == [("https://x.example/blog/a", "Useful article")]
