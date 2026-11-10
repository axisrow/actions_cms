import pytest
import yaml

from actions_cms import config
from actions_cms.errors import ConfigError
from helpers import RUBRICS, make_site


def write(root, data):
    root.mkdir(parents=True, exist_ok=True)
    (root / "cms.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_defaults(tmp_path):
    site = make_site(tmp_path)
    root = tmp_path.resolve()
    assert site.root == root
    assert site.generator == "mkdocs-material"
    assert (site.drafts, site.posts, site.index) == (
        root / "drafts", root / "docs/blog/posts", root / "content/index.json")
    assert site.required == ("title", "date", "rubric", "status", "summary")
    assert site.summary_max == 280
    assert (site.feeds.config, site.feeds.inbox, site.feeds.hours, site.feeds.user_agent) == (
        root / "config/sources.yaml", root / "inbox/news", 48, None)
    assert (site.sites.config, site.sites.inbox) == (root / "config/sites.yaml", root / "inbox/sites")
    assert "actions-cms-bot" in site.sites.user_agent


def test_an_existing_layout_is_expressed_in_config(tmp_path):
    write(tmp_path, {
        "rubrics": {"news": "Новости", "deep": "Матчасть", "misc": None},
        "paths": {"posts": "site_src/posts", "index": "data/registry.json"},
        "required": ["summary", "sources"],
        "summary_max": 0,
        "collect": {
            "feeds": {"hours": 12, "user_agent": "custom/1.0"},
            "sites": {"config": "config/competitors.yaml", "inbox": "inbox/competitors", "user_agent": "bot/2.0"},
        },
    })
    site = config.load(tmp_path)
    root = tmp_path.resolve()
    assert site.rubrics == {"news": "Новости", "deep": "Матчасть", "misc": None}
    assert site.posts == root / "site_src/posts" and site.index == root / "data/registry.json"
    assert site.required == ("title", "date", "rubric", "status", "summary", "sources")
    assert site.summary_max == 0
    assert (site.feeds.hours, site.feeds.user_agent) == (12, "custom/1.0")
    assert site.sites.config == root / "config/competitors.yaml"
    assert site.sites.inbox == root / "inbox/competitors"
    assert site.sites.user_agent == "bot/2.0"


@pytest.mark.parametrize("data, fragment", [
    ({}, "rubrics is required"),
    ({"rubrics": {}}, "rubrics is required"),
    ({"rubrics": {"news": ["News"]}}, "rubrics must map"),
    ({"rubrics": RUBRICS, "rubric": {}}, "unknown key: rubric"),
    ({"rubrics": RUBRICS, "paths": {"post": "x"}}, "unknown key in paths: post"),
    ({"rubrics": RUBRICS, "collect": {"feeds": {"hour": 1}}}, "unknown key in collect.feeds: hour"),
    ({"rubrics": RUBRICS, "paths": {"posts": "../elsewhere"}}, "outside the site"),
    ({"rubrics": RUBRICS, "paths": {"posts": "/etc"}}, "outside the site"),
    ({"rubrics": RUBRICS, "summary_max": "long"}, "summary_max"),
    ({"rubrics": RUBRICS, "collect": {"feeds": {"hours": 0}}}, "collect.feeds.hours"),
    ({"rubrics": RUBRICS, "required": "summary"}, "required must be a list"),
])
def test_bad_config_is_rejected(tmp_path, data, fragment):
    write(tmp_path, data)
    with pytest.raises(ConfigError, match=fragment):
        config.load(tmp_path)


def test_root_is_found_from_a_subfolder(tmp_path, monkeypatch):
    make_site(tmp_path / "site")
    monkeypatch.chdir(tmp_path / "site" / "docs" / "blog")
    assert config.load().root == (tmp_path / "site").resolve()


def test_no_site_here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="cms.yaml not found"):
        config.load()
    with pytest.raises(ConfigError, match="no cms.yaml here"):
        config.load(tmp_path)
