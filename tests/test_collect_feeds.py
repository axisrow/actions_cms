import json
from datetime import datetime, timezone

import feedparser
import pytest
import yaml

from actions_cms.collect import feeds
from actions_cms.errors import ConfigError
from helpers import make_site

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def rss(*items: tuple[str, str, str, str]) -> str:
    """A feed of (title, link, pubDate, description)."""
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link><pubDate>{date}</pubDate><description>{d}</description></item>"
        for t, link, date, d in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>{body}</channel></rss>'


FEEDS = {
    "https://a.example/feed": rss(
        ("Fresh <b>widgets</b> arrive", "https://a.example/1", "Thu, 15 Jan 2026 09:00:00 GMT", "About widgets."),
        ("Older gadget story", "https://a.example/2", "Wed, 14 Jan 2026 09:00:00 GMT", "About gadgets."),
        ("Ancient history", "https://a.example/3", "Mon, 05 Jan 2026 09:00:00 GMT", "Too old."),
        ("Sponsored widgets", "https://a.example/4", "Thu, 15 Jan 2026 10:00:00 GMT", "An advertisement."),
    ),
    "https://b.example/feed": rss(
        ("Widgets on sale", "https://b.example/1", "Thu, 15 Jan 2026 11:00:00 GMT", "Prices."),
        ("Unrelated sports news", "https://b.example/2", "Thu, 15 Jan 2026 11:30:00 GMT", "Football."),
    ),
    "https://dead.example/feed": "this is not a feed",
}
SOURCES = {
    "keywords": ["widget"],
    "exclude": ["advertisement"],
    "feeds": [
        {"name": "Dead", "url": "https://dead.example/feed"},
        {"name": "A", "url": "https://a.example/feed"},
        {"name": "B", "url": "https://b.example/feed", "filter": True},
    ],
}


def fake_parse(calls=None):
    def parse(url, **kwargs):
        if calls is not None:
            calls.append((url, kwargs))
        return feedparser.parse(FEEDS[url])
    return parse


@pytest.fixture
def site(tmp_path):
    site = make_site(tmp_path)
    site.feeds.config.parent.mkdir()
    site.feeds.config.write_text(yaml.safe_dump(SOURCES), encoding="utf-8")
    return site


def test_collects_fresh_filtered_items_newest_first(site, capsys):
    out = feeds.collect(site, parse=fake_parse(), now=NOW)
    assert out == site.feeds.inbox / "2026-01-15.json"
    items = json.loads(out.read_text(encoding="utf-8"))
    assert [(i["source"], i["url"]) for i in items] == [
        ("B", "https://b.example/1"),  # keyword filter kept it, dropped the sports item
        ("A", "https://a.example/1"),
        ("A", "https://a.example/2"),  # unfiltered feed: no keyword needed; the old and the excluded items are gone
    ]
    assert items[1] == {
        "title": "Fresh widgets arrive",  # markup stripped
        "url": "https://a.example/1",
        "source": "A",
        "published": "2026-01-15T09:00:00+00:00",
        "summary": "About widgets.",
    }
    assert "! Dead:" in capsys.readouterr().out  # a dead feed is reported and skipped


def test_the_age_limit_can_be_overridden(site):
    out = feeds.collect(site, hours=6, parse=fake_parse(), now=NOW)
    urls = [i["url"] for i in json.loads(out.read_text(encoding="utf-8"))]
    assert urls == ["https://b.example/1", "https://a.example/1"]


def test_a_second_run_adds_nothing(site):
    out = feeds.collect(site, parse=fake_parse(), now=NOW)
    before = out.read_bytes()
    assert feeds.collect(site, parse=fake_parse(), now=NOW) is None
    assert out.read_bytes() == before


def test_no_file_is_created_when_there_is_nothing(site):
    site.feeds.config.write_text(yaml.safe_dump({"feeds": []}), encoding="utf-8")
    assert feeds.collect(site, parse=fake_parse(), now=NOW) is None
    assert not site.feeds.inbox.exists()


def test_the_user_agent_is_sent_only_when_configured(tmp_path):
    for agent, expected in ((None, {}), ("custom/1.0", {"agent": "custom/1.0"})):
        root = tmp_path / str(agent)
        cms = {"rubrics": {"news": "News"}, "collect": {"feeds": {"user_agent": agent}}} if agent else None
        site = make_site(root, cms=cms)
        site.feeds.config.parent.mkdir()
        site.feeds.config.write_text(yaml.safe_dump({"feeds": [SOURCES["feeds"][1]]}), encoding="utf-8")
        calls = []
        feeds.collect(site, parse=fake_parse(calls), now=NOW)
        assert calls == [("https://a.example/feed", expected)]


def test_bad_or_missing_config(tmp_path):
    site = make_site(tmp_path)
    with pytest.raises(ConfigError, match="collector config not found"):
        feeds.collect(site, parse=fake_parse(), now=NOW)
    site.feeds.config.parent.mkdir()
    site.feeds.config.write_text(yaml.safe_dump({"feeds": [{"name": "No url"}]}), encoding="utf-8")
    with pytest.raises(ConfigError, match="every feed needs `name` and `url`"):
        feeds.collect(site, parse=fake_parse(), now=NOW)
