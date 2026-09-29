"""Preview one file; writing requires --write."""

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

import libcst as cst

from . import RECIPES, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    migrate = commands.add_parser("run")
    migrate.add_argument("recipe", choices=RECIPES)
    migrate.add_argument("path", type=Path)
    migrate.add_argument(
        "--target-python", required=True, help="Lowest supported Python, e.g. 3.11"
    )
    migrate.add_argument("--write", action="store_true")
    migrate.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "list":
        print(json.dumps(RECIPES, indent=2))
        return
    try:
        if args.path.is_symlink() or args.path.suffix not in (".py", ".pyi"):
            raise ValueError(
                "Expected a regular .py or .pyi file; symlinks are unsupported"
            )
        raw = args.path.read_bytes()
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        result = preview(
            raw.decode(encoding), args.recipe, args.target_python, str(args.path)
        )
        if args.write and result["changed"]:
            data = result["source"].encode(encoding)
            with tempfile.NamedTemporaryFile(
                dir=args.path.parent, delete=False
            ) as temp:
                temporary = Path(temp.name)
            try:
                with temporary.open("wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.chmod(args.path.stat().st_mode)
                if args.path.read_bytes() != raw:
                    raise ValueError("File changed during preview; retry")
                os.replace(temporary, args.path)
            finally:
                temporary.unlink(missing_ok=True)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result["diff"], end="")
            print(result["guidance"], file=sys.stderr)
            for reason in result["skipped"]:
                print(reason, file=sys.stderr)
    except (
        OSError,
        ValueError,
        SyntaxError,
        cst.ParserSyntaxError,
        subprocess.TimeoutExpired,
    ) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
