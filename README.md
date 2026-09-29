# python-e18e codemods

Explicit source migrations for the [python-e18e initiative](https://github.com/python-e18e/python-e18e).
Requires Python 3.11+ to run; each recipe separately checks the target project's
lowest supported Python. LibCST preserves import formatting and comments;
[Ruff UP033](https://docs.astral.sh/ruff/rules/lru-cache-with-maxsize-none/)
provides the cache pattern rewrite.

From a checkout of this repository:

```sh
uv sync --locked
uv run --locked python-e18e-codemod list
uv run --locked python-e18e-codemod run tomli-to-tomllib /path/to/file.py --target-python 3.11
```

The default output is a unified diff. Add `--json` for transformed source,
`changed`, `diff`, `skipped`, guidance, and a reference URL. After reviewing the
diff, repeat with `--write` to replace that one file atomically. File encoding,
line endings, and permissions are preserved. Symlinks are rejected.

| Recipe | Target floor | Scope and review |
| --- | --- | --- |
| `tomli-to-tomllib` | 3.11 | `load`, `loads`, and `TOMLDecodeError`; check parser behavior. |
| `appdirs-to-platformdirs` | 3.10 | Common directory helpers and `AppDirs`; install a compatible platformdirs release and check paths on every supported OS. |
| `backports-zoneinfo-to-zoneinfo` | 3.9 | Public zoneinfo imports; retain `tzdata` when needed and check timezone transitions. |
| `lru-cache-to-cache` | 3.9 | Ruff's safe `UP033` fix; review remaining findings. |

```python
import tomli
# becomes: import tomllib as tomli

from appdirs import user_cache_dir
# becomes: from platformdirs import user_cache_dir

from backports.zoneinfo import ZoneInfo
# becomes: from zoneinfo import ZoneInfo
```

Aliases keep existing local references intact. Wildcards, unsupported imported
symbols, relative imports, and unaliased dotted imports are not rewritten.
An ordinary module import is rewritten without auditing every attribute used
later: these recipes are opt-in mechanical previews, not API compatibility
proofs. Audit private APIs, dynamic imports, local modules with matching names,
and compatibility fallback blocks before accepting a diff.

Dependency declarations and lockfiles need separate review after inventorying
all package use. Keep environment markers for supported older interpreters.
No recipe removes dependencies or claims a performance improvement.

The runnable check covers aliases, comments, unchanged unsupported forms,
Python floors, idempotence, encoding, and file writes:

```sh
uv run --locked python checks/check_codemods.py
```

See [the rollout](https://github.com/python-e18e/python-e18e/blob/main/docs/migrations.md) for pilot work and release gates.
