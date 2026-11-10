"""Tests that the built artefact contains the package (CON-46).

The defect these exist to prevent was invisible for five tickets. `pyproject.toml`
listed `packages = ["constat"]`, setuptools took it literally, and every
subpackage — `git`, `store`, `evidence`, `ai` — was dropped from the wheel. The
development install is editable and imports from the working tree, so every
test passed while the shippable artefact would have failed at the first
`from .store import …`.

The lesson is about the *class* of bug rather than the instance. An explicit
list has to be remembered on every new subpackage, and forgetting it produces a
broken artefact rather than an error — so the configuration is asserted to use
discovery, not merely to be correct today.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import sysconfig
import tomllib
import zipfile
from fnmatch import fnmatch
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
PACKAGE_ROOT = PROJECT_ROOT / "constat"


def config() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def packages_config():
    packages = config()["tool"]["setuptools"]["packages"]
    assert isinstance(packages, dict), (
        f"packages is {packages!r} — an explicit list silently drops "
        "subpackages from the wheel (CON-46)"
    )
    return packages


def include_patterns() -> list[str]:
    return list(packages_config()["find"]["include"])


def subpackages_on_disk() -> set[str]:
    """Every importable package under `constat/`, as a dotted name."""
    found = {"constat"}
    for init in PACKAGE_ROOT.rglob("__init__.py"):
        relative = init.parent.relative_to(PROJECT_ROOT)
        found.add(".".join(relative.parts))
    return found


class TestTheBuildConfiguration:
    def test_packages_are_discovered_not_listed(self):
        """A list is the defect. Discovery cannot forget a new subpackage."""
        assert "find" in packages_config(), (
            "packages must be a find directive; an explicit list silently drops "
            "subpackages from the wheel (CON-46)"
        )

    def test_every_subpackage_on_disk_matches_an_include_pattern(self):
        """The check that would have failed before the fix.

        Runs against the directory tree rather than a hardcoded list, so a
        subpackage added in a later ticket is covered without anyone
        remembering to extend this test.
        """
        patterns = include_patterns()
        for package in sorted(subpackages_on_disk()):
            assert any(fnmatch(package, p) for p in patterns), (
                f"{package} matches none of {patterns} and would be missing "
                "from the wheel"
            )

    def test_the_subpackages_are_actually_found(self):
        """Guard the guard: if the tree walk found nothing, the test above
        would pass while asserting nothing at all."""
        found = subpackages_on_disk()
        assert {"constat", "constat.ai", "constat.git", "constat.store"} <= found

    def test_namespace_packages_stay_off(self):
        """With namespaces on, any directory becomes a package — including
        `__pycache__` and stray data directories."""
        assert packages_config()["find"]["namespaces"] is False


BUILD_INPUTS = ("pyproject.toml", "README.md", "LICENSE", "NOTICE")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """A real wheel, built once for this module from a **staged** source tree.

    The staging is not tidiness. Building in place reuses setuptools'
    `build/lib` directory, which is never cleaned, so a module that landed
    there during an earlier build is included in every later wheel regardless
    of what `pyproject.toml` now says. That masked the CON-46 defect while this
    test was being written: with the broken configuration restored, an in-tree
    build still produced a complete wheel. A build that cannot be made to fail
    is not a check.

    Skips rather than fails when the environment cannot build one: the build
    needs the setuptools backend, which this project installs as neither a
    runtime nor a dev dependency, so it may have to be fetched.
    """
    staged = tmp_path_factory.mktemp("staged")
    shutil.copytree(
        PACKAGE_ROOT,
        staged / "constat",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in BUILD_INPUTS:
        shutil.copy2(PROJECT_ROOT / name, staged / name)

    target = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-deps", "--quiet", "--no-cache-dir",
            "--wheel-dir", str(target),
            str(staged),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    built = list(target.glob("*.whl"))
    if result.returncode != 0 or not built:
        pytest.skip(f"cannot build a wheel here: {result.stderr.strip()[-200:]}")
    return built[0]


class TestTheBuiltWheel:
    """The real check.

    The configuration tests above run unconditionally and catch the same
    defect; these prove it against an actual artefact.
    """

    def test_it_contains_every_module_in_the_package(self, wheel: Path):
        shipped = {
            name for name in zipfile.ZipFile(wheel).namelist() if name.endswith(".py")
        }
        expected = {
            str(path.relative_to(PROJECT_ROOT))
            for path in PACKAGE_ROOT.rglob("*.py")
            if "__pycache__" not in path.parts
        }
        assert expected <= shipped

    def test_the_wheel_is_importable_on_its_own(self, wheel: Path, tmp_path: Path):
        """Unpack it and import the CLI with nothing else able to help.

        `constat.cli` reaches `store`, `git`, `evidence` and `ai` through its
        own imports, so a missing subpackage is an `ImportError` here — which
        is what the broken wheel would have done to a real user.

        Run with `-S` on purpose. The editable development install registers a
        meta path finder through a `.pth` file, and that finder claims
        `constat.*` from the working tree: with site processing on, this test
        imported `cli` from the wheel and `store` from the repository, and
        passed against a wheel that was missing `store` entirely. `-S` skips
        `.pth` files, so the only `constat` available is the unpacked one;
        site-packages is appended by hand for pydantic.
        """
        extracted = tmp_path / "unpacked"
        zipfile.ZipFile(wheel).extractall(extracted)

        probe = (
            "import sys;"
            f"sys.path[:0] = [{str(extracted)!r}];"
            f"sys.path.append({sysconfig.get_paths()['purelib']!r});"
            "import constat.cli, constat.store, constat.git, constat.evidence,"
            " constat.ai;"
            "assert all(m.__file__.startswith(%r) for m in ("
            "constat.cli, constat.store, constat.git, constat.evidence,"
            " constat.ai)), [m.__file__ for m in (constat.cli, constat.store)];"
            "print(constat.cli.build_parser().prog)" % str(extracted)
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", probe],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "constat"
