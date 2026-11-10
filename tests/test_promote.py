import datetime as dt

import pytest

from actions_cms import promote
from actions_cms.content import load_index, read_frontmatter
from actions_cms.errors import ContentError
from helpers import BODY, draft, make_site, post, snapshot


def test_a_draft_becomes_a_post(site):
    source = draft(site, tags=["a"])
    moves = promote.promote(site, approve_all=True)

    target = site.posts / "2026-01-15-first-post.md"
    assert [(m.draft, m.target) for m in moves] == [(source, target)]
    assert not source.exists() and not source.parent.exists()  # the emptied batch folder goes too
    meta, body = read_frontmatter(target)
    assert body == BODY
    assert meta["status"] == "approved"
    # the category is derived from the rubric and sits next to it; the slug is appended last
    assert list(meta) == ["title", "date", "rubric", "categories", "summary", "status", "tags", "slug"]
    assert meta["categories"] == ["News"] and meta["slug"] == "first-post"
    assert load_index(site.index) == [{
        "slug": "first-post", "title": "First post", "date": "2026-01-15", "rubric": "news",
        "tags": ["a"], "status": "approved", "path": "docs/blog/posts/2026-01-15-first-post.md",
    }]


def test_categories_written_by_the_author_are_kept(site):
    draft(site, categories=["News", "Guides"])
    promote.promote(site, approve_all=True)
    meta, _ = read_frontmatter(site.posts / "2026-01-15-first-post.md")
    assert meta["categories"] == ["News", "Guides"]


def test_a_rubric_without_a_category_adds_none(tmp_path):
    site = make_site(tmp_path, cms={"rubrics": {"note": None}})
    draft(site, rubric="note")
    promote.promote(site, approve_all=True)
    meta, _ = read_frontmatter(site.posts / "2026-01-15-first-post.md")
    assert "categories" not in meta


def test_the_file_is_named_after_the_front_matter_date_not_the_folder(site):
    draft(site, batch="batch-7", date=dt.date(2026, 2, 3))
    promote.promote(site, approve_all=True)
    assert (site.posts / "2026-02-03-first-post.md").exists()


def test_a_datetime_gives_a_plain_date_in_the_file_name(site):
    draft(site, date=dt.datetime(2026, 2, 3, 10, 30))
    promote.promote(site, approve_all=True)
    assert (site.posts / "2026-02-03-first-post.md").exists()


def test_without_all_only_approved_drafts_move(site):
    draft(site, "01-ready.md", status="approved")
    waiting = draft(site, "02-waiting.md")
    moves = promote.promote(site)
    assert [m.target.name for m in moves] == ["2026-01-15-ready.md"]
    assert waiting.exists()
    assert {i["slug"]: i["status"] for i in load_index(site.index)} == {"ready": "approved", "waiting": "draft"}


def test_no_drafts_is_not_an_error(site):
    assert promote.promote(site, approve_all=True) == []


@pytest.mark.parametrize("name, overrides, body, fragment", [
    ("01-first-post.md", {"rubric": "opinion"}, BODY, "unknown rubric 'opinion'"),
    ("01-first-post.md", {"summary": None}, BODY, "missing summary"),
    ("01-first-post.md", {"title": ""}, BODY, "missing title"),
    ("01-first-post.md", {}, "\nLead only, no separator.\n", "no excerpt separator <!-- more -->"),
    ("01-first-post.md", {"date": "2026-01-15"}, BODY, "unquoted YAML date"),
    ("01-статья.md", {}, BODY, "is not latin"),
    ("01-first-post.md", {"summary": "x" * 281}, BODY, "summary is 281 characters"),
    ("01-first-post.md", {"tags": "one, two"}, BODY, "tags must be a list"),
    ("01-first-post.md", {"categories": ["Opinion"]}, BODY, "categories not allowed on this site: Opinion"),
    ("01-first-post.md", {"categories": ["Guides"]}, BODY, "categories must include 'News'"),
    ("01-first-post.md", {"categories": "News"}, BODY, "categories must be a list"),
    ("01-first-post.md", {"slug": "another-slug"}, BODY, "differs from the file name"),
])
def test_one_bad_draft_stops_the_whole_batch(site, name, overrides, body, fragment):
    draft(site, "02-good.md", title="Good")
    bad = draft(site, name, body=body, **overrides)
    before = snapshot(site.root)
    with pytest.raises(ContentError) as e:
        promote.promote(site, approve_all=True)
    assert {p.path for p in e.value.problems} == {bad}
    assert any(fragment in p.message for p in e.value.problems)
    assert snapshot(site.root) == before  # nothing moved, nothing written


def test_all_problems_are_reported_at_once(site):
    draft(site, "01-a.md", rubric="opinion", summary=None)
    draft(site, "02-b.md", body="\nNo separator.\n")
    _, problems = promote.plan(site, approve_all=True)
    assert len(problems) == 3


def test_two_drafts_with_one_slug_collide_across_batches(site):
    draft(site, "01-same.md", batch="2026-01-15")
    second = draft(site, "03-same.md", batch="2026-01-16", date=dt.date(2026, 1, 16))
    with pytest.raises(ContentError) as e:
        promote.promote(site, approve_all=True)
    assert [p.path for p in e.value.problems] == [second]
    assert "slug 'same' is also used by drafts/2026-01-15/01-same.md" in e.value.problems[0].message


def test_a_published_post_is_never_overwritten(site):
    published = post(site, "2026-01-15-first-post.md", title="The original")
    draft(site)
    before = published.read_bytes()
    with pytest.raises(ContentError, match="slug 'first-post' is already published"):
        promote.promote(site, approve_all=True)
    assert published.read_bytes() == before


def test_a_slug_published_on_another_date_is_taken_too(site):
    post(site, "2025-12-01-first-post.md")
    draft(site)
    with pytest.raises(ContentError, match="already published: docs/blog/posts/2025-12-01-first-post.md"):
        promote.promote(site, approve_all=True)


def test_a_malformed_published_post_blocks_publication_before_anything_moves(site):
    broken = post(site, "2026-01-01-handwritten.md", summary=None)  # the index rebuild would choke on it
    draft(site)
    before = snapshot(site.root)
    with pytest.raises(ContentError) as e:
        promote.promote(site, approve_all=True)
    assert [(p.path, p.message) for p in e.value.problems] == [(broken, "missing summary")]
    assert snapshot(site.root) == before


def test_an_unparseable_draft_is_reported_even_without_all(site):
    path = site.drafts / "2026-01-15" / "01-broken.md"
    path.parent.mkdir(parents=True)
    path.write_text("no front-matter\n", encoding="utf-8")
    with pytest.raises(ContentError, match="no front-matter"):
        promote.promote(site)
