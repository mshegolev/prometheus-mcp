#!/usr/bin/env python3
"""Bump the package version across every carrier — surgically and idempotently.

The version of this package lives in four places, and a release is only
coherent when all four agree:

* ``pyproject.toml``                   — ``version = "X.Y.Z"`` inside ``[project]``
* ``src/prometheus_mcp/__init__.py``   — the ``__version__`` assignment
* ``server.json``                      — top-level ``"version"``
* ``server.json``                      — ``"version"`` of the PyPI package entry

``glama.json`` carries no version and is deliberately left alone.

Every edit here changes *only* the version. ``__init__.py`` is rewritten by
regex substitution on its ``__version__`` line, so the module docstring and any
re-exports survive; ``server.json`` is edited as parsed JSON, so no text-level
``sed`` can accidentally hit a version-looking string elsewhere in the file.
Running the tool twice with the same target version is a no-op.

Usage::

    scripts/bump_version.py --bump patch      # 0.5.0 -> 0.5.1, prints new version
    scripts/bump_version.py --set 1.2.3       # explicit target, prints it back
    scripts/bump_version.py --check           # exit 1 if the carriers disagree

``--root`` points the tool at a different checkout (used by the tests to run
the real bump logic against throwaway copies of the files).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PYPI_IDENTIFIER = "prometheus-mcp"
INIT_RELPATH = Path("src") / "prometheus_mcp" / "__init__.py"

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_PROJECT_SECTION_RE = re.compile(r"^\[project\]\s*$", re.MULTILINE)
_ANY_SECTION_RE = re.compile(r"^\[", re.MULTILINE)
_TOML_VERSION_RE = re.compile(r"""^(?P<lead>version\s*=\s*)(?P<q>["'])(?P<ver>[^"']+)(?P=q)""", re.MULTILINE)
_DUNDER_VERSION_RE = re.compile(
    r"""^(?P<lead>__version__\s*(?::\s*str\s*)?=\s*)(?P<q>["'])(?P<ver>[^"']+)(?P=q)""",
    re.MULTILINE,
)


class VersionError(RuntimeError):
    """A carrier could not be read or written."""


# --------------------------------------------------------------------------- #
# pyproject.toml
# --------------------------------------------------------------------------- #


def _project_section(text: str) -> tuple[int, int]:
    """Return the ``[start, end)`` character span of the ``[project]`` table."""
    header = _PROJECT_SECTION_RE.search(text)
    if header is None:
        raise VersionError("pyproject.toml has no [project] section")
    start = header.end()
    nxt = _ANY_SECTION_RE.search(text, start)
    return start, nxt.start() if nxt else len(text)


def read_pyproject_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start, end = _project_section(text)
    match = _TOML_VERSION_RE.search(text, start, end)
    if match is None:
        raise VersionError(f'no `version = "..."` line in [project] of {path}')
    return match.group("ver")


def write_pyproject_version(path: Path, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    start, end = _project_section(text)
    match = _TOML_VERSION_RE.search(text, start, end)
    if match is None:
        raise VersionError(f'no `version = "..."` line in [project] of {path}')
    if match.group("ver") == version:
        return False
    new_text = f'{text[: match.start()]}{match.group("lead")}"{version}"{text[match.end() :]}'
    path.write_text(new_text, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# src/prometheus_mcp/__init__.py
# --------------------------------------------------------------------------- #


def read_init_version(path: Path) -> str:
    match = _DUNDER_VERSION_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise VersionError(f'no `__version__ = "..."` assignment in {path}')
    return match.group("ver")


def write_init_version(path: Path, version: str) -> bool:
    """Replace only the ``__version__`` line; the rest of the module is untouched."""
    text = path.read_text(encoding="utf-8")
    match = _DUNDER_VERSION_RE.search(text)
    if match is None:
        raise VersionError(f'no `__version__ = "..."` assignment in {path}')
    if match.group("ver") == version:
        return False
    new_text = f'{text[: match.start()]}{match.group("lead")}"{version}"{text[match.end() :]}'
    path.write_text(new_text, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# server.json
# --------------------------------------------------------------------------- #


def _pypi_packages(data: dict) -> list[dict]:
    packages = data.get("packages") or []
    matches = [
        pkg
        for pkg in packages
        if isinstance(pkg, dict) and (pkg.get("registryType") == "pypi" or pkg.get("identifier") == PYPI_IDENTIFIER)
    ]
    if not matches:
        raise VersionError("server.json has no PyPI package entry to keep in sync")
    return matches


def read_server_json_versions(path: Path) -> dict[str, str]:
    """Return every version field of ``server.json``, keyed by a readable label."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" not in data:
        raise VersionError("server.json has no top-level `version`")
    versions = {"server.json:version": data["version"]}
    for idx, pkg in enumerate(_pypi_packages(data)):
        if "version" not in pkg:
            raise VersionError("server.json PyPI package entry has no `version`")
        versions[f"server.json:packages[{idx}].version"] = pkg["version"]
    return versions


def write_server_json_version(path: Path, version: str) -> bool:
    """Set the JSON version fields. Parsed-JSON edit, never a text substitution."""
    data = json.loads(path.read_text(encoding="utf-8"))
    packages = _pypi_packages(data)
    changed = data.get("version") != version or any(pkg.get("version") != version for pkg in packages)
    if not changed:
        return False
    data["version"] = version
    for pkg in packages:
        pkg["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #


def carrier_versions(root: Path) -> dict[str, str]:
    """Every version carrier in the repo, keyed by a human-readable label."""
    versions = {
        "pyproject.toml": read_pyproject_version(root / "pyproject.toml"),
        str(INIT_RELPATH.as_posix()): read_init_version(root / INIT_RELPATH),
    }
    versions.update(read_server_json_versions(root / "server.json"))
    return versions


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def apply_version(root: Path, version: str) -> list[str]:
    """Write ``version`` into every carrier. Returns the files actually changed."""
    changed: list[str] = []
    if write_pyproject_version(root / "pyproject.toml", version):
        changed.append("pyproject.toml")
    if write_init_version(root / INIT_RELPATH, version):
        changed.append(INIT_RELPATH.as_posix())
    if write_server_json_version(root / "server.json", version):
        changed.append("server.json")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bump", choices=("major", "minor", "patch"), help="increment part of the current version")
    group.add_argument("--set", dest="explicit", metavar="X.Y.Z", help="set this exact version")
    group.add_argument("--check", action="store_true", help="verify all carriers agree; exit 1 if they do not")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="repository root")
    parser.add_argument("--quiet", action="store_true", help="print nothing but the resulting version")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()

    try:
        current = carrier_versions(root)
    except (VersionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        distinct = set(current.values())
        if len(distinct) == 1:
            print(distinct.pop())
            return 0
        print("error: version carriers disagree:", file=sys.stderr)
        for label, value in current.items():
            print(f"  {label}: {value}", file=sys.stderr)
        return 1

    if args.explicit:
        target = args.explicit
    else:
        target = bump(current["pyproject.toml"], args.bump)

    if not _SEMVER_RE.match(target):
        print(f"error: {target!r} is not a MAJOR.MINOR.PATCH version", file=sys.stderr)
        return 2

    try:
        changed = apply_version(root, target)
    except (VersionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        for name in changed:
            print(f"updated {name}", file=sys.stderr)
        if not changed:
            print(f"already at {target}, nothing to do", file=sys.stderr)
    print(target)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
