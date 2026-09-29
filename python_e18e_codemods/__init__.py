"""Explicit, formatting-preserving migration previews."""

import ast
import difflib
import re
import subprocess
import sys

import libcst as cst
from libcst.helpers import get_full_name_for_node

RECIPES = {
    "tomli-to-tomllib": {
        "module": "tomli",
        "replacement": "tomllib",
        "minimum_python": "3.11",
        "symbols": ["load", "loads", "TOMLDecodeError"],
        "guidance": "Read-only TOML APIs. Check parser errors and supported Python versions; retain conditional backports for older runtimes.",
        "source": "https://docs.python.org/3/library/tomllib.html",
    },
    "appdirs-to-platformdirs": {
        "module": "appdirs",
        "replacement": "platformdirs",
        "minimum_python": "3.10",
        "symbols": [
            "AppDirs",
            "user_data_dir",
            "site_data_dir",
            "user_config_dir",
            "site_config_dir",
            "user_cache_dir",
            "user_state_dir",
            "user_log_dir",
        ],
        "guidance": "Install a compatible platformdirs release. Paths can change across operating systems; test storage locations and migrate existing data before release.",
        "source": "https://platformdirs.readthedocs.io/en/latest/api.html",
    },
    "backports-zoneinfo-to-zoneinfo": {
        "module": "backports.zoneinfo",
        "replacement": "zoneinfo",
        "minimum_python": "3.9",
        "symbols": [
            "ZoneInfo",
            "ZoneInfoNotFoundError",
            "InvalidTZPathWarning",
            "TZPATH",
            "reset_tzpath",
            "available_timezones",
        ],
        "guidance": "Keep tzdata where no system IANA database exists. Test timezone data availability and daylight-saving transitions.",
        "source": "https://docs.python.org/3/library/zoneinfo.html#data-sources",
    },
    "lru-cache-to-cache": {
        "minimum_python": "3.9",
        "ruff_rule": "UP033",
        "guidance": "Ruff's safe UP033 fix replaces lru_cache(maxsize=None). typed=True and comments may prevent a safe rewrite.",
        "source": "https://docs.astral.sh/ruff/rules/lru-cache-with-maxsize-none/",
    },
}


def python_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"3\.\d+", value):
        raise ValueError("target_python must be an explicit minimum such as 3.11")
    version = tuple(map(int, value.split(".")))
    if version > sys.version_info[:2]:
        raise ValueError("target_python exceeds the running interpreter")
    return version


class ImportMigration(cst.CSTTransformer):
    def __init__(self, recipe):
        self.recipe = recipe
        self.skipped = []

    def leave_Import(self, original, updated):
        aliases = []
        for alias in updated.names:
            name = get_full_name_for_node(alias.name)
            if name == self.recipe["module"]:
                if "." in name and alias.asname is None:
                    self.skipped.append(
                        f"Unaliased dotted import {name}: rewrite qualified uses manually."
                    )
                else:
                    alias = alias.with_changes(
                        name=cst.parse_expression(self.recipe["replacement"]),
                        asname=alias.asname or cst.AsName(cst.Name(name)),
                    )
            aliases.append(alias)
        return updated.with_changes(names=aliases)

    def leave_ImportFrom(self, original, updated):
        if (
            updated.relative
            or get_full_name_for_node(updated.module) != self.recipe["module"]
        ):
            return updated
        if isinstance(updated.names, cst.ImportStar) or any(
            get_full_name_for_node(alias.name) not in self.recipe["symbols"]
            for alias in updated.names
        ):
            self.skipped.append(
                "Wildcard or unsupported symbol import: review manually."
            )
            return updated
        return updated.with_changes(
            module=cst.parse_expression(self.recipe["replacement"])
        )


def preview(
    source: str, recipe_id: str, target_python: str, filename="source.py"
) -> dict:
    """Return transformed source and a diff; never execute the supplied source."""
    if recipe_id not in RECIPES:
        raise ValueError(f"Unknown recipe: {recipe_id}")
    recipe = RECIPES[recipe_id]
    target = python_version(target_python)
    if target < python_version(recipe["minimum_python"]):
        raise ValueError(f"{recipe_id} requires Python {recipe['minimum_python']}+")
    ast.parse(source, feature_version=target)
    skipped = []
    if "ruff_rule" in recipe:
        # ponytail: one upstream rule; extend the allowlist when another recipe is validated.
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--isolated",
                "--select",
                recipe["ruff_rule"],
                "--target-version",
                f"py{target[0]}{target[1]}",
                "--fix",
                "--no-unsafe-fixes",
                "--stdin-filename",
                "source.py",
                "-",
            ],
            input=source,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode not in (0, 1):
            raise ValueError(result.stderr.strip() or "Ruff failed")
        transformed = result.stdout
        if result.returncode == 1:
            skipped.append(
                "Ruff left findings that require manual review or unsafe fixes."
            )
    else:
        migration = ImportMigration(recipe)
        transformed = cst.parse_module(source).visit(migration).code
        skipped = migration.skipped
    ast.parse(transformed, feature_version=target)
    return {
        "recipe": recipe_id,
        "changed": transformed != source,
        "source": transformed,
        "diff": "".join(
            line
            if line.endswith(("\n", "\r"))
            else line + "\n\\ No newline at end of file\n"
            for line in difflib.unified_diff(
                source.splitlines(keepends=True),
                transformed.splitlines(keepends=True),
                fromfile=filename,
                tofile=filename,
            )
        ),
        "skipped": skipped,
        "guidance": recipe["guidance"],
        "reference": recipe["source"],
    }
