"""A new site from the template, through validation, publication and a real MkDocs build."""
import datetime as dt

import pytest

pytest.importorskip("material", reason="needs the dev extra: mkdocs-material")

from actions_cms import config, generators, promote, validate  # noqa: E402
from actions_cms.cli import main  # noqa: E402
from actions_cms.init import init  # noqa: E402
from helpers import draft, snapshot  # noqa: E402

TODAY = dt.date(2026, 1, 15)


@pytest.fixture
def site(tmp_path):
    init(tmp_path / "site", name="Demo", repo="owner/demo", lang="en", today=TODAY)
    return config.load(tmp_path / "site")


def test_an_empty_blog_builds(site):
    (site.drafts / "2026-01-15" / "01-hello-world.md").unlink()
    assert generators.get(site.generator).build(site, capture=True).returncode == 0


def test_preview_build_then_publish_then_build(site):
    before = snapshot(site.root)
    ok, output = validate.preview_build(site)
    assert ok, output
    assert snapshot(site.root) == before  # the trial ran in a copy
    assert str(site.root) in output and "cms-preview-" not in output  # paths point at the real site

    promote.promote(site, approve_all=True)
    assert main(["--root", str(site.root), "build"]) == 0
    built = site.root / "site"
    assert (built / "blog/2026/01/15/hello-world/index.html").is_file()  # latin URL from the file name
    assert (built / "blog/category/guides/index.html").is_file()  # category derived from the rubric
    assert "hello-world" in (built / "feed_rss_created.xml").read_text(encoding="utf-8")


def test_preview_build_catches_what_static_checks_cannot(site, capsys):
    draft(site, "02-broken-link.md", rubric="news", body="\nLead.\n\n<!-- more -->\n\nSee [this page](missing-page.md).\n")
    assert validate.static(site) == []
    before = snapshot(site.root)
    assert main(["--root", str(site.root), "validate", "--build"]) == 1
    captured = capsys.readouterr()
    assert "missing-page.md" in captured.out and "preview build failed" in captured.err
    assert snapshot(site.root) == before
