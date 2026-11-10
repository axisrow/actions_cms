import pytest

from actions_cms import generators, validate
from actions_cms.errors import ConfigError
from actions_cms.generators import mkdocs_material as gen
from helpers import MKDOCS, draft, make_site


def test_unknown_generator(tmp_path):
    with pytest.raises(ConfigError, match="unknown generator 'hugo'"):
        generators.get("hugo")
    assert generators.get("mkdocs-material") is gen


def test_settings_defaults_without_a_config(tmp_path):
    site = make_site(tmp_path, mkdocs=None)
    blog = gen.settings(site)
    assert not blog.enabled and not blog.excerpt_required
    assert blog.separator == "<!-- more -->" and blog.categories_allowed == ()
    assert gen.output_dir(site) == site.root / "site"


def test_settings_read_the_blog_plugin(tmp_path):
    site = make_site(tmp_path, mkdocs="""\
docs_dir: src
site_dir: public
plugins:
  - search
  - blog:
      blog_dir: journal
      post_excerpt: required
      post_excerpt_separator: "<!-- cut -->"
      categories_allowed: [News, Guides]
""")
    blog = gen.settings(site)
    assert blog.enabled and blog.excerpt_required
    assert blog.posts == site.root / "src" / "journal" / "posts"
    assert blog.separator == "<!-- cut -->" and blog.categories_allowed == ("News", "Guides")
    assert gen.output_dir(site) == site.root / "public"


@pytest.mark.parametrize("plugins", [
    "plugins:\n  - blog\n",
    "plugins:\n  - material/blog:\n      post_excerpt: optional\n",
    "plugins:\n  blog: {}\n  search: {}\n",
])
def test_the_blog_plugin_is_recognised_in_every_spelling(tmp_path, plugins):
    assert gen.settings(make_site(tmp_path, mkdocs=plugins)).enabled


def test_python_tags_in_mkdocs_yml_are_tolerated(tmp_path):
    site = make_site(tmp_path, mkdocs="""\
site_name: !ENV [SITE_NAME, "Fallback"]
markdown_extensions:
  - pymdownx.emoji:
      emoji_index: !!python/name:material.extensions.emoji.twemoji
plugins:
  - blog:
      post_excerpt: required
""")
    assert gen.settings(site).excerpt_required


def test_broken_mkdocs_yml_is_a_config_error(tmp_path):
    site = make_site(tmp_path, mkdocs="plugins: [unclosed\n")
    with pytest.raises(ConfigError, match="mkdocs.yml: invalid YAML"):
        gen.settings(site)


def test_a_healthy_site_has_no_problems(site):
    draft(site)
    assert validate.static(site) == []


@pytest.mark.parametrize("mkdocs, fragment", [
    (None, "not found"),
    ("plugins:\n  - search\n", "the blog plugin is not enabled"),
    ("plugins:\n  - blog:\n      blog_dir: journal\n", "renders posts from docs/journal/posts"),
    ("plugins:\n  - blog:\n      categories_allowed: [News]\n", "categories_allowed lacks rubric categories: Guides"),
])
def test_site_misconfiguration_is_reported(tmp_path, mkdocs, fragment):
    site = make_site(tmp_path, mkdocs=mkdocs)
    problems = gen.check_site(site)
    assert len(problems) == 1 and fragment in problems[0].message


def test_categories_allowed_in_mkdocs_yml_narrows_the_choice(tmp_path):
    site = make_site(tmp_path, cms={"rubrics": {"news": "News"}}, mkdocs=MKDOCS + "      categories_allowed: [News, Extra]\n")
    blog = gen.settings(site)
    ok = {"rubric": "news", "categories": ["News", "Extra"]}
    assert gen.check_post(site, blog, ok, "lead\n<!-- more -->\n") == []
    bad = {"rubric": "news", "categories": ["News", "Other"]}
    assert gen.check_post(site, blog, bad, "lead\n<!-- more -->\n") == ["categories not allowed on this site: Other"]


def test_the_separator_is_optional_unless_mkdocs_requires_it(tmp_path):
    site = make_site(tmp_path, mkdocs="plugins:\n  - blog\n")
    draft(site, body="\nJust a lead.\n")
    assert validate.static(site) == []
