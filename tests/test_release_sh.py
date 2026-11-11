"""scripts/release.sh against a local bare repository."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release.sh"
pytestmark = pytest.mark.skipif(not (shutil.which("git") and shutil.which("bash")), reason="needs git and bash")


class Repo:
    def __init__(self, tmp_path: Path, version: str = "0.0.1"):
        self.tmp = tmp_path
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.remote = tmp_path / "remote.git"
        self.git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(self.remote))
        self.work = tmp_path / "work"
        self.git(tmp_path, "init", "--quiet", "--initial-branch=main", str(self.work))
        self.git(self.work, "remote", "add", "origin", str(self.remote))
        self.set_version(version)

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def set_version(self, version: str) -> None:
        init = self.work / "src" / "actions_cms" / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text(f'"""doc"""\n\n__version__ = "{version}"\n')
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "--quiet", "--allow-empty", "-m", f"version {version}")
        self.git(self.work, "push", "--quiet", "origin", "HEAD:refs/heads/main")

    def run(self, mode: str, **env: str) -> subprocess.CompletedProcess:
        output = self.tmp / "github_output"
        output.write_text("")
        result = subprocess.run(["bash", str(SCRIPT), mode], cwd=self.work, capture_output=True, text=True,
                                env={**self.env, "GITHUB_OUTPUT": str(output), **env})
        result.github_output = output.read_text()
        return result

    def tags(self) -> dict[str, str]:
        """tag name -> commit it points to (annotated tags peeled)."""
        names = self.git(self.remote, "for-each-ref", "--format=%(refname:short)", "refs/tags").split()
        return {name: self.git(self.remote, "rev-parse", f"{name}^{{commit}}").strip() for name in names}

    def head(self) -> str:
        return self.git(self.work, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_a_manual_release_creates_the_tag_and_the_major_tag(repo):
    result = repo.run("dispatch")
    assert result.returncode == 0, result.stderr
    assert result.github_output == "tag=v0.0.1\n"
    assert repo.tags() == {"v0.0.1": repo.head(), "v0": repo.head()}
    assert repo.git(repo.remote, "cat-file", "-t", "v0.0.1").strip() == "tag"  # annotated
    assert repo.git(repo.remote, "tag", "-n1", "-l", "v0.0.1").split(None, 1)[1].strip() == "actions_cms 0.0.1"


def test_a_manual_release_refuses_an_existing_tag_and_changes_nothing(repo):
    assert repo.run("dispatch").returncode == 0
    before = repo.tags()
    repo.set_version("0.0.1")  # a new commit, but the same version
    result = repo.run("dispatch")
    assert result.returncode == 1
    assert "tag v0.0.1 already exists" in result.stdout
    assert result.github_output == ""
    assert repo.tags() == before  # neither v0.0.1 nor v0 moved


def test_the_major_tag_follows_the_newest_release(repo):
    assert repo.run("dispatch").returncode == 0
    repo.set_version("0.1.0")
    assert repo.run("dispatch").returncode == 0
    assert repo.tags() == {"v0.0.1": repo.tags()["v0.0.1"], "v0.1.0": repo.head(), "v0": repo.head()}
    assert repo.tags()["v0.0.1"] != repo.head()
    repo.set_version("1.0.0")
    assert repo.run("dispatch").returncode == 0
    assert {"v1", "v0"} <= set(repo.tags()) and repo.tags()["v1"] == repo.head() and repo.tags()["v0"] != repo.head()


def test_a_pushed_tag_must_match_the_version(repo):
    repo.git(repo.work, "tag", "-a", "v0.0.1", "-m", "x")
    ok = repo.run("pushed", GITHUB_REF_NAME="v0.0.1")
    assert ok.returncode == 0, ok.stderr
    assert repo.tags() == {"v0": repo.head()}  # only the major tag is created here: the pushed tag is the user's

    bad = repo.run("pushed", GITHUB_REF_NAME="v0.0.2")
    assert bad.returncode == 1 and "does not match the package version 0.0.1" in bad.stdout


def test_bad_usage(repo):
    assert repo.run("nonsense").returncode == 2
    (repo.work / "src" / "actions_cms" / "__init__.py").write_text("no version here\n")
    result = repo.run("dispatch")
    assert result.returncode == 1 and "could not read __version__" in result.stdout
