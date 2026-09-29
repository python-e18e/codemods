"""Run from this checkout: uv run python checks/check_codemods.py."""

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from python_e18e_codemods import preview


def check():
    cases = [
        (
            "tomli-to-tomllib",
            "3.11",
            'import tomli  # keep\ntext = "import tomli"\nvalue = tomli.loads("x=1")\n',
            'import tomllib as tomli  # keep\ntext = "import tomli"\nvalue = tomli.loads("x=1")\n',
        ),
        (
            "tomli-to-tomllib",
            "3.11",
            "from tomli import (\n    loads as parse,  # keep\n)\n",
            "from tomllib import (\n    loads as parse,  # keep\n)\n",
        ),
        (
            "appdirs-to-platformdirs",
            "3.10",
            "import os, appdirs as dirs\n",
            "import os, platformdirs as dirs\n",
        ),
        (
            "backports-zoneinfo-to-zoneinfo",
            "3.9",
            "from backports.zoneinfo import ZoneInfo as TZ\nimport backports.zoneinfo as zi\n",
            "from zoneinfo import ZoneInfo as TZ\nimport zoneinfo as zi\n",
        ),
        (
            "lru-cache-to-cache",
            "3.9",
            "import functools\n@functools.lru_cache(maxsize=None)\ndef f(): return 1\n",
            "import functools\n@functools.cache\ndef f(): return 1\n",
        ),
    ]
    for recipe, target, source, expected in cases:
        result = preview(source, recipe, target)
        assert result["source"] == expected, result
        assert result["changed"] and result["diff"]
        ast.parse(expected)
        assert not preview(expected, recipe, target)["changed"]
    result = preview("import tomli", "tomli-to-tomllib", "3.11")
    assert result["source"] == "import tomllib as tomli"
    assert "-import tomli\n\\ No newline at end of file\n" in result["diff"]
    assert not preview(
        "import functools\n@functools.lru_cache(maxsize=None, typed=True)\ndef f(): pass\n",
        "lru-cache-to-cache",
        "3.9",
    )["changed"]
    for source in (
        "from tomli import *\n",
        "from tomli import loads, unknown\n",
        "from .tomli import loads\n",
    ):
        assert not preview(source, "tomli-to-tomllib", "3.11")["changed"]
    result = preview(
        "import backports.zoneinfo\n", "backports-zoneinfo-to-zoneinfo", "3.11"
    )
    assert not result["changed"] and result["skipped"]
    for recipe, target, source in (
        ("tomli-to-tomllib", "3.10", "import tomli\n"),
        ("lru-cache-to-cache", "3.8", "import functools\n"),
        ("missing", "3.11", "pass\n"),
        ("tomli-to-tomllib", ">=3.11", "pass\n"),
        ("tomli-to-tomllib", "3.11", "invalid !\n"),
    ):
        try:
            preview(source, recipe, target)
        except (ValueError, SyntaxError):
            pass
        else:
            raise AssertionError("Invalid recipe, source, or Python floor accepted")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "sample.py"
        original = b"# coding: latin-1\r\n# caf\xe9\r\nimport tomli\r\n"
        path.write_bytes(original)
        path.chmod(0o640)
        command = [
            sys.executable,
            "-m",
            "python_e18e_codemods",
            "run",
            "tomli-to-tomllib",
            str(path),
            "--target-python",
            "3.11",
            "--json",
        ]
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        assert json.loads(result.stdout)["changed"] and path.read_bytes() == original
        subprocess.run([*command, "--write"], check=True, capture_output=True)
        expected = original.replace(b"import tomli", b"import tomllib as tomli")
        assert path.read_bytes() == expected and path.stat().st_mode & 0o777 == 0o640
        subprocess.run([*command, "--write"], check=True, capture_output=True)
        assert path.read_bytes() == expected
        link = root / "link.py"
        link.symlink_to(path)
        result = subprocess.run(
            [*command[:5], str(link), *command[6:], "--write"],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2 and path.read_bytes() == expected


if __name__ == "__main__":
    check()
    print("Codemod and file safety checks passed.")
