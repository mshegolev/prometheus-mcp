"""The version carriers must never drift apart, and bumping must not destroy files.

Four files carry the package version — ``pyproject.toml``, the package
``__init__``, and *two* fields in ``server.json``. ``server.json`` once silently
lagged at 0.2.0 for a month because the release tooling never touched it
(fixed by hand in a4531d5). These tests make that drift a red build instead of
a discovery, and they exercise ``scripts/bump_version.py`` against throwaway
copies so a regression to the old file-clobbering bump is caught here too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import prometheus_mcp

REPO_ROOT = Path(__file__).resolve().parents[1]
BUMP_SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"

sys.path.insert(0, str(BUMP_SCRIPT.parent))
import bump_version  # noqa: E402  (imported after sys.path is extended)


def _run_bump(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUMP_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """A throwaway copy of the three version-carrying files."""
    (tmp_path / "src" / "prometheus_mcp").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy(REPO_ROOT / "server.json", tmp_path / "server.json")
    shutil.copy(
        REPO_ROOT / "src" / "prometheus_mcp" / "__init__.py",
        tmp_path / "src" / "prometheus_mcp" / "__init__.py",
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# the guarantee itself: every carrier agrees
# --------------------------------------------------------------------------- #


def test_all_version_carriers_agree() -> None:
    """pyproject, __init__, and both server.json fields report one version."""
    carriers = bump_version.carrier_versions(REPO_ROOT)

    assert len(carriers) == 4, f"expected 4 version carriers, found {sorted(carriers)}"
    distinct = set(carriers.values())
    assert len(distinct) == 1, f"version carriers disagree: {carriers}"


def test_runtime_dunder_version_matches_the_manifests() -> None:
    """The value importable at runtime is the one the manifests advertise."""
    assert prometheus_mcp.__version__ == bump_version.read_pyproject_version(REPO_ROOT / "pyproject.toml")


def test_server_json_pypi_entry_is_covered() -> None:
    """The nested PyPI package version is a real carrier, not just the top-level one."""
    versions = bump_version.read_server_json_versions(REPO_ROOT / "server.json")
    assert "server.json:version" in versions
    assert any(key.startswith("server.json:packages[") for key in versions)


def test_glama_json_carries_no_version() -> None:
    """glama.json is intentionally not synced — assert it has nothing to sync."""
    glama = json.loads((REPO_ROOT / "glama.json").read_text(encoding="utf-8"))
    assert "version" not in glama


def test_check_mode_passes_on_the_real_repo() -> None:
    result = _run_bump("--check")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == prometheus_mcp.__version__


# --------------------------------------------------------------------------- #
# the bump itself: surgical, complete, idempotent
# --------------------------------------------------------------------------- #


def test_bump_preserves_module_docstring(sandbox: Path) -> None:
    """The old workflow did ``echo ... > __init__.py`` and ate the docstring."""
    init = sandbox / "src" / "prometheus_mcp" / "__init__.py"
    original = init.read_text(encoding="utf-8")
    docstring_line = original.splitlines()[0]
    assert docstring_line.startswith('"""'), "fixture precondition: module starts with a docstring"

    result = _run_bump("--root", str(sandbox), "--set", "9.9.9")
    assert result.returncode == 0, result.stderr

    updated = init.read_text(encoding="utf-8")
    assert docstring_line in updated, "module docstring was destroyed by the version bump"
    assert '__version__ = "9.9.9"' in updated
    # Only the version line changed.
    assert [ln for ln in original.splitlines() if "__version__" not in ln] == [
        ln for ln in updated.splitlines() if "__version__" not in ln
    ]


def test_bump_updates_every_carrier(sandbox: Path) -> None:
    result = _run_bump("--root", str(sandbox), "--set", "9.9.9")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "9.9.9"

    carriers = bump_version.carrier_versions(sandbox)
    assert set(carriers.values()) == {"9.9.9"}, carriers


def test_bump_preserves_server_json_content(sandbox: Path) -> None:
    """Only the two version fields move; schema, env vars, and key order survive."""
    before = json.loads((sandbox / "server.json").read_text(encoding="utf-8"))
    _run_bump("--root", str(sandbox), "--set", "9.9.9")
    after = json.loads((sandbox / "server.json").read_text(encoding="utf-8"))

    assert list(before) == list(after), "top-level key order changed"
    before["version"] = after["version"] = None
    for pkg in (*before["packages"], *after["packages"]):
        pkg["version"] = None
    assert before == after, "server.json lost or reordered content outside the version fields"


def test_bump_is_idempotent(sandbox: Path) -> None:
    _run_bump("--root", str(sandbox), "--set", "9.9.9")
    snapshot = {p: p.read_bytes() for p in sorted(sandbox.rglob("*")) if p.is_file()}

    result = _run_bump("--root", str(sandbox), "--set", "9.9.9")
    assert result.returncode == 0, result.stderr
    assert "nothing to do" in result.stderr

    assert {p: p.read_bytes() for p in sorted(sandbox.rglob("*")) if p.is_file()} == snapshot


@pytest.mark.parametrize(
    ("part", "expected"),
    [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")],
)
def test_bump_arithmetic(part: str, expected: str) -> None:
    assert bump_version.bump("1.2.3", part) == expected


def test_check_mode_detects_drift(sandbox: Path) -> None:
    """A lagging server.json — the exact a4531d5 failure — must fail the check."""
    server = sandbox / "server.json"
    data = json.loads(server.read_text(encoding="utf-8"))
    data["version"] = "0.2.0"
    server.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = _run_bump("--root", str(sandbox), "--check")
    assert result.returncode == 1
    assert "disagree" in result.stderr
    assert "0.2.0" in result.stderr


def test_rejects_a_non_semver_target(sandbox: Path) -> None:
    result = _run_bump("--root", str(sandbox), "--set", "not-a-version")
    assert result.returncode == 2
    assert bump_version.carrier_versions(sandbox)["pyproject.toml"] != "not-a-version"
