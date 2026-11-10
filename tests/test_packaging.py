"""The wheel must carry the whole site template, dot-files included — `cms init` reads it from there."""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "src" / "actions_cms" / "template"


def test_the_wheel_contains_the_whole_template(tmp_path):
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--quiet", "--no-deps", "--wheel-dir", str(tmp_path), str(ROOT)],
        check=True,
    )
    (wheel,) = tmp_path.glob("actions_cms-*.whl")
    prefix = "actions_cms/template/"
    packaged = {n[len(prefix):] for n in zipfile.ZipFile(wheel).namelist() if n.startswith(prefix)}
    on_disk = {p.relative_to(TEMPLATE).as_posix() for p in TEMPLATE.rglob("*") if p.is_file()}
    assert packaged == on_disk
    assert {".gitignore", ".github/workflows/publish.yml", "drafts/.gitkeep"} <= packaged
