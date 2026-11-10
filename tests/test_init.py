import datetime as dt
import re

import pytest
import yaml

from actions_cms import config, validate
from actions_cms.content import load_index, read_frontmatter
from actions_cms.errors import ConfigError
from actions_cms.init import init, pages_url

TODAY = dt.date(2026, 1, 15)
EXPECTED = {
    ".github/dependabot.yml",
    ".github/workflows/check.yml",
    ".github/workflows/collect.yml",
    ".github/workflows/pages.yml",
    ".github/workflows/publish.yml",
    ".gitignore",
    "README.md",
    "cms.yaml",
    "config/sites.yaml",
    "config/sources.yaml",
    "content/index.json",
    "docs/blog/index.md",
    "docs/blog/posts/.gitkeep",
    "docs/index.md",
    "drafts/.gitkeep",
    "drafts/2026-01-15/01-hello-world.md",
    "mkdocs.yml",
    "requirements.txt",
}


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def create(target, **kwargs):
    return init(target, **{"name": "Test site", "repo": "owner/site", "today": TODAY, **kwargs})


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_init_renders_a_complete_valid_site(tmp_path, lang):
    written, skipped = create(tmp_path, lang=lang)
    assert files(tmp_path) == EXPECTED
    assert set(written) == EXPECTED - {"content/index.json"} and skipped == []
    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"__[A-Z][A-Z0-9_]*__", text), f"token left in {path}"
        if path.suffix in (".yml", ".yaml"):
            yaml.safe_load(text)

    site = config.load(tmp_path)
    assert validate.static(site) == []
    assert [(i["slug"], i["status"]) for i in load_index(site.index)] == [("hello-world", "draft")]
    meta, _ = read_frontmatter(tmp_path / "drafts/2026-01-15/01-hello-world.md")
    assert meta["date"] == TODAY and meta["rubric"] in site.rubrics


def test_language_picks_labels_and_prose(tmp_path):
    create(tmp_path / "ru", lang="ru")
    create(tmp_path / "en", lang="en")
    ru, en = (yaml.safe_load((tmp_path / lang / "mkdocs.yml").read_text(encoding="utf-8")) for lang in ("ru", "en"))
    assert ru["theme"]["language"] == "ru" and en["theme"]["language"] == "en"
    assert list(ru["nav"][0]) == ["Главная"] and list(en["nav"][0]) == ["Home"]
    assert config.load(tmp_path / "ru").rubrics == {"news": "Новости", "guide": "Гайды"}
    assert config.load(tmp_path / "en").rubrics == {"news": "News", "guide": "Guides"}
    assert "Как выходит статья" in (tmp_path / "ru" / "README.md").read_text(encoding="utf-8")
    assert "How a post gets published" in (tmp_path / "en" / "README.md").read_text(encoding="utf-8")


def test_site_identity_lands_in_the_config(tmp_path):
    name = 'Oils: "facts" & myths — №1'
    create(tmp_path, name=name, description="Line with: colon", engine_ref="main")
    mkdocs = yaml.safe_load((tmp_path / "mkdocs.yml").read_text(encoding="utf-8"))
    assert mkdocs["site_name"] == name  # quotes and colons survive the YAML
    assert mkdocs["site_description"] == "Line with: colon"
    assert mkdocs["site_url"] == "https://owner.github.io/site/"
    assert mkdocs["repo_url"] == "https://github.com/owner/site"
    publish = yaml.safe_load((tmp_path / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    assert publish["jobs"]["promote"]["steps"][1]["uses"] == "axisrow/actions_cms@main"
    assert f"# {name}" in (tmp_path / "docs/index.md").read_text(encoding="utf-8")


def test_the_engine_ref_defaults_to_the_major_tag(tmp_path):
    create(tmp_path)
    assert "uses: axisrow/actions_cms@v0\n" in (tmp_path / ".github/workflows/collect.yml").read_text(encoding="utf-8")


def test_existing_files_are_kept_unless_forced(tmp_path):
    (tmp_path / "README.md").write_text("mine\n", encoding="utf-8")
    written, skipped = create(tmp_path)
    assert skipped == ["README.md"] and "README.md" not in written
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "mine\n"
    written, skipped = create(tmp_path, force=True)
    assert skipped == [] and "README.md" in written
    assert (tmp_path / "README.md").read_text(encoding="utf-8") != "mine\n"


def test_pages_url():
    assert pages_url("owner/site") == "https://owner.github.io/site/"
    assert pages_url("Owner/owner.github.io") == "https://Owner.github.io/"


@pytest.mark.parametrize("kwargs, fragment", [
    ({"repo": "not-a-repo"}, "owner/name"),
    ({"lang": "de"}, "unknown language"),
])
def test_bad_arguments(tmp_path, kwargs, fragment):
    with pytest.raises(ConfigError, match=fragment):
        create(tmp_path, **kwargs)
    assert files(tmp_path) == set()
