import pytest

from actions_cms import dedup, index
from actions_cms.content import load_index, save_index
from actions_cms.errors import ContentError
from helpers import draft, post


def test_sync_lists_posts_and_drafts_sorted_by_date(site):
    draft(site, "01-new-draft.md", title="New draft", tags=["a"])
    post(site, "2026-01-10-old-post.md", title="Old post")
    assert index.sync(site) == (["new-draft", "old-post"], [])
    assert load_index(site.index) == [
        {"slug": "old-post", "title": "Old post", "date": "2026-01-15", "rubric": "news", "tags": [],
         "status": "approved", "path": "docs/blog/posts/2026-01-10-old-post.md"},
        {"slug": "new-draft", "title": "New draft", "date": "2026-01-15", "rubric": "news", "tags": ["a"],
         "status": "draft", "path": "drafts/2026-01-15/01-new-draft.md"},
    ]


def test_sync_drops_entries_whose_file_is_gone(site):
    post(site)
    save_index(site.index, [{"slug": "ghost", "title": "Deleted draft", "date": "2026-01-01", "rubric": "news",
                             "tags": [], "status": "draft", "path": "drafts/2026-01-01/01-ghost.md"}])
    assert index.sync(site) == (["old-post"], ["ghost"])
    assert [i["slug"] for i in load_index(site.index)] == ["old-post"]


def test_sync_does_not_rewrite_an_up_to_date_index(site):
    post(site)
    index.sync(site)
    stamp = site.index.stat().st_mtime_ns
    assert index.sync(site) == ([], [])
    assert site.index.stat().st_mtime_ns == stamp


def test_sync_is_all_or_nothing(site):
    post(site)
    index.sync(site)
    before = site.index.read_bytes()
    draft(site, "01-no-summary.md", summary=None)
    draft(site, "02-old-post.md")  # same slug as the published post
    with pytest.raises(ContentError) as e:
        index.sync(site)
    messages = [p.message for p in e.value.problems]
    assert any("missing summary" in m for m in messages)
    assert any("slug 'old-post' is already used" in m for m in messages)
    assert site.index.read_bytes() == before


def test_dedup_finds_close_titles(site):
    post(site, "2026-01-10-a.md", title="How to choose engine oil for winter")
    post(site, "2026-01-11-b.md", title="Brake fluid: when to change it")
    index.sync(site)
    hits = dedup.similar(site, "How to choose an engine oil for winter")
    assert [item["slug"] for _, item in hits] == ["a"]
    assert hits[0][0] > 0.9
    assert dedup.similar(site, "Something entirely different") == []
    assert len(dedup.similar(site, "Brake fluid", threshold=0.3)) >= 1
