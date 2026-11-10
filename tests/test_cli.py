import json

import pytest

from actions_cms.cli import main
from helpers import draft, post, snapshot


def run(site, *argv):
    return main(["--root", str(site.root), *argv])


def test_validate_passes_and_fails(site, capsys):
    draft(site)
    assert run(site, "validate") == 0
    assert "1 draft(s) OK" in capsys.readouterr().out

    draft(site, "02-bad.md", rubric="opinion")
    assert run(site, "validate") == 1
    assert "drafts/2026-01-15/02-bad.md: unknown rubric 'opinion'" in capsys.readouterr().err


def test_promote_then_nothing_left(site, capsys):
    draft(site)
    assert run(site, "promote", "--all") == 0
    assert "drafts/2026-01-15/01-first-post.md -> docs/blog/posts/2026-01-15-first-post.md" in capsys.readouterr().out
    assert run(site, "promote", "--all") == 0
    assert "no drafts to publish" in capsys.readouterr().out
    assert run(site, "promote") == 0
    assert "no approved drafts" in capsys.readouterr().out


def test_a_failed_promote_changes_nothing_and_exits_1(site, capsys):
    draft(site, body="\nNo separator.\n")
    before = snapshot(site.root)
    assert run(site, "promote", "--all") == 1
    assert "no excerpt separator" in capsys.readouterr().err
    assert snapshot(site.root) == before


def test_index_sync_and_dedup(site, capsys):
    post(site, title="How to choose engine oil for winter")
    assert run(site, "index", "sync") == 0
    assert "+ old-post" in capsys.readouterr().out
    assert json.loads(site.index.read_text(encoding="utf-8"))[0]["slug"] == "old-post"

    assert run(site, "dedup", "How to choose an engine oil for winter") == 1
    assert "docs/blog/posts/2026-01-10-old-post.md" in capsys.readouterr().out
    assert run(site, "dedup", "Entirely different") == 0


def test_root_is_accepted_after_the_subcommand(site):
    draft(site)
    assert main(["validate", "--root", str(site.root)]) == 0


def test_config_problems_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["validate"]) == 2
    assert "cms.yaml not found" in capsys.readouterr().err
    assert main(["--root", str(tmp_path), "collect", "feeds"]) == 2


def test_collect_skips_collectors_without_a_config(site, capsys):
    assert run(site, "collect") == 0
    out = capsys.readouterr().out
    assert "feeds: config/sources.yaml not found, skipped" in out
    assert "sites: config/sites.yaml not found, skipped" in out
    assert run(site, "collect", "sites") == 2  # asked for by name: its config must exist


def test_problems_become_annotations_on_github(site, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(site.root.parent))
    draft(site, "01-bad.md", summary=None)
    assert run(site, "validate") == 1
    assert "::error file=site/drafts/2026-01-15/01-bad.md::missing summary" in capsys.readouterr().out


def test_init_creates_a_site(tmp_path, capsys):
    target = tmp_path / "new"
    assert main(["init", str(target), "--name", "New site", "--repo", "owner/new", "--lang", "en"]) == 0
    assert (target / "cms.yaml").is_file()
    assert main(["--root", str(target), "validate"]) == 0
    assert main(["init", str(target), "--name", "New site", "--repo", "bad"]) == 2


def test_usage_errors_exit_2():
    with pytest.raises(SystemExit) as e:
        main(["no-such-command"])
    assert e.value.code == 2
