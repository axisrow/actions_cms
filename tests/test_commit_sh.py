"""scripts/commit.sh against a local bare repository: the push race that three site workflows can run into."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "commit.sh"
pytestmark = pytest.mark.skipif(not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash")


class Repo:
    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        # isolate from the developer's git configuration (signing, hooks, default branch)
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "tester@example.com",
        }
        self.remote = tmp_path / "remote.git"
        self.git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(self.remote))
        self.work = self.clone("work")
        (self.work / "README.md").write_text("site\n")
        (self.work / "docs").mkdir()
        (self.work / "docs" / "page.md").write_text("one\n")
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "--quiet", "-m", "init")
        self.git(self.work, "push", "--quiet", "origin", "HEAD:refs/heads/main")
        self.git(self.work, "branch", "--quiet", "--set-upstream-to=origin/main")

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def clone(self, name: str) -> Path:
        path = self.tmp / name
        self.git(self.tmp, "clone", "--quiet", str(self.remote), str(path))
        if not self.git(path, "branch", "--show-current").strip():
            self.git(path, "checkout", "--quiet", "-b", "main")  # cloned while the remote was still empty
        return path

    def push_from_elsewhere(self, relpath: str, text: str) -> None:
        """Another workflow gets its commit in first."""
        other = self.clone(f"other-{len(list(self.tmp.iterdir()))}")
        target = other / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        self.git(other, "add", "-A")
        self.git(other, "commit", "--quiet", "-m", f"other: {relpath}")
        self.git(other, "push", "--quiet", "origin", "HEAD:refs/heads/main")

    def commit(self, paths: str, message: str = "publish: {date}", **env: str) -> subprocess.CompletedProcess:
        output = self.tmp / "github_output"
        output.write_text("")
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=self.work, capture_output=True, text=True,
            env={**self.env, "CMS_COMMIT_PATHS": paths, "CMS_COMMIT_MESSAGE": message,
                 "CMS_PUSH_BACKOFF": "0", "GITHUB_OUTPUT": str(output), **env},
        )
        result.github_output = output.read_text()
        return result

    def remote_log(self) -> list[str]:
        return self.git(self.remote, "log", "--format=%s", "main").splitlines()

    def remote_file(self, relpath: str) -> str:
        return self.git(self.remote, "show", f"main:{relpath}")


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_changes_are_committed_and_pushed(repo):
    (repo.work / "docs" / "page.md").write_text("two\n")
    (repo.work / "content").mkdir()
    (repo.work / "content" / "index.json").write_text("[]\n")
    (repo.work / "unrelated.txt").write_text("left alone\n")
    result = repo.commit("drafts docs content", "publish: {date} at {datetime}")
    assert result.returncode == 0, result.stderr
    assert result.github_output == "changed=true\n"
    subject = repo.remote_log()[0]
    assert subject.startswith("publish: 20") and "{" not in subject  # both tokens expanded
    assert repo.remote_file("docs/page.md") == "two\n" and repo.remote_file("content/index.json") == "[]\n"
    assert "unrelated.txt" not in repo.git(repo.remote, "ls-tree", "-r", "--name-only", "main")
    assert repo.git(repo.remote, "log", "-1", "--format=%an", "main").strip() == "Tester"


def test_deletions_are_committed(repo):
    (repo.work / "docs" / "page.md").unlink()
    assert repo.commit("docs").github_output == "changed=true\n"
    assert "docs/page.md" not in repo.git(repo.remote, "ls-tree", "-r", "--name-only", "main")


def test_the_bot_identity_is_the_default(repo):
    (repo.work / "docs" / "page.md").write_text("two\n")
    del repo.env["GIT_AUTHOR_NAME"], repo.env["GIT_AUTHOR_EMAIL"], repo.env["GIT_COMMITTER_NAME"], repo.env["GIT_COMMITTER_EMAIL"]
    assert repo.commit("docs").returncode == 0
    assert repo.git(repo.remote, "log", "-1", "--format=%an <%ae>", "main").strip() == (
        "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>")


@pytest.mark.parametrize("paths", ["docs", "inbox", "inbox docs", ""])
def test_nothing_to_commit(repo, paths):
    result = repo.commit(paths)  # `inbox` does not exist yet: skipped, not an error
    assert result.returncode == 0, result.stderr
    assert result.github_output == "changed=false\n"
    assert repo.remote_log() == ["init"]


def test_paths_may_span_lines(repo):
    (repo.work / "docs" / "page.md").write_text("two\n")
    (repo.work / "inbox").mkdir()
    (repo.work / "inbox" / "a.json").write_text("[]\n")
    assert repo.commit("docs\ninbox").github_output == "changed=true\n"
    assert repo.remote_file("inbox/a.json") == "[]\n"


def test_a_concurrent_push_to_other_files_is_survived(repo):
    repo.push_from_elsewhere("inbox/news.json", "[]\n")  # the collector won the race
    (repo.work / "docs" / "page.md").write_text("two\n")
    result = repo.commit("docs")
    assert result.returncode == 0, result.stderr
    assert "rebasing onto origin/main" in result.stderr
    assert result.github_output == "changed=true\n"
    assert repo.remote_log()[1:] == ["other: inbox/news.json", "init"]
    assert repo.remote_file("docs/page.md") == "two\n" and repo.remote_file("inbox/news.json") == "[]\n"


def test_local_files_outside_the_commit_do_not_block_the_rebase(repo):
    repo.push_from_elsewhere("inbox/news.json", "[]\n")
    (repo.work / "docs" / "page.md").write_text("two\n")
    (repo.work / "README.md").write_text("edited but not committed\n")
    result = repo.commit("docs")
    assert result.returncode == 0, result.stderr
    assert repo.remote_file("README.md") == "site\n"
    assert (repo.work / "README.md").read_text() == "edited but not committed\n"


def test_a_conflicting_push_fails_without_touching_the_remote(repo):
    repo.push_from_elsewhere("docs/page.md", "theirs\n")
    (repo.work / "docs" / "page.md").write_text("ours\n")
    result = repo.commit("docs")
    assert result.returncode == 1
    assert "the remote changed the same files" in result.stderr
    assert result.github_output == ""
    assert repo.remote_log() == ["other: docs/page.md", "init"]
    assert repo.remote_file("docs/page.md") == "theirs\n"
    assert not (repo.work / ".git" / "rebase-merge").exists()  # the rebase was aborted, the clone is usable


def test_an_unreachable_remote_fails_after_the_attempts(repo):
    (repo.work / "docs" / "page.md").write_text("two\n")
    result = repo.commit("docs", CMS_REMOTE="nowhere", CMS_PUSH_ATTEMPTS="2")
    assert result.returncode == 1
    assert "push failed after 2 attempts" in result.stderr


def test_a_detached_head_is_refused(repo):
    repo.git(repo.work, "checkout", "--quiet", "--detach")
    (repo.work / "docs" / "page.md").write_text("two\n")
    result = repo.commit("docs")
    assert result.returncode == 1 and "HEAD is detached" in result.stderr
    assert repo.remote_log() == ["init"]
