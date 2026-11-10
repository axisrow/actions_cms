import datetime as dt

import pytest

from actions_cms.content import load_index, read_frontmatter, save_index, slug_of, write_frontmatter
from actions_cms.errors import ContentError


def test_roundtrip_keeps_meta_and_body(tmp_path):
    path = tmp_path / "a.md"
    meta = {"title": "Заголовок", "date": dt.date(2026, 1, 15), "tags": ["a", "b"]}
    body = "\nLead.\n\n<!-- more -->\n\nText.\n"
    write_frontmatter(path, meta, body)
    assert read_frontmatter(path) == (meta, body)
    # rewriting what was read must not change a byte
    before = path.read_bytes()
    write_frontmatter(path, *read_frontmatter(path))
    assert path.read_bytes() == before


def test_dashes_inside_a_value_do_not_end_the_block(tmp_path):
    path = tmp_path / "a.md"
    path.write_text('---\ntitle: "Before --- after"\nstatus: draft\n---\n\nBody.\n', encoding="utf-8")
    meta, body = read_frontmatter(path)
    assert meta == {"title": "Before --- after", "status": "draft"}
    assert body == "\n\nBody.\n"


def test_horizontal_rule_in_the_body_is_kept(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\ntitle: T\n---\n\nOne.\n\n---\n\nTwo.\n", encoding="utf-8")
    meta, body = read_frontmatter(path)
    assert meta == {"title": "T"}
    assert body == "\n\nOne.\n\n---\n\nTwo.\n"


@pytest.mark.parametrize("text", [
    "No front-matter at all.\n",
    "---\ntitle: never closed\n",
    "---\ntitle: [unbalanced\n---\n",
    "---\n- a list\n- not a mapping\n---\n",
])
def test_bad_front_matter_is_a_content_error(tmp_path, text):
    path = tmp_path / "a.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContentError) as e:
        read_frontmatter(path)
    assert e.value.problems[0].path == path
    assert isinstance(e.value, ValueError)  # what site-side scripts caught before the engine existed


@pytest.mark.parametrize("name, slug", [
    ("01-my-post.md", "my-post"),
    ("2026-01-15-my-post.md", "my-post"),
    ("my-post.md", "my-post"),
    ("05-5w30-vs-5w40.md", "5w30-vs-5w40"),
])
def test_slug_of_strips_the_prefix(tmp_path, name, slug):
    assert slug_of(tmp_path / name) == slug


@pytest.mark.parametrize("name", ["01-статья.md", "01-My-Post.md", "01-my_post.md", "01-.md", "01-my--post.md"])
def test_slug_of_rejects_non_latin_names(tmp_path, name):
    with pytest.raises(ContentError):
        slug_of(tmp_path / name)


def test_index_roundtrip(tmp_path):
    path = tmp_path / "content" / "index.json"
    assert load_index(path) == []
    save_index(path, [{"slug": "a", "title": "Заголовок"}])
    assert load_index(path) == [{"slug": "a", "title": "Заголовок"}]
    assert "Заголовок" in path.read_text(encoding="utf-8")  # not \u-escaped
    assert path.read_text(encoding="utf-8").endswith("\n")
