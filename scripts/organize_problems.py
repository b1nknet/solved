"""Move root-level solution files into directories grouped by problem number."""

import re
import sys
from pathlib import Path
from shutil import move


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    exit_code = 0

    for source in sorted(root.iterdir()):
        if not re.fullmatch(r"[0-9]+", source.stem):
            continue
        if source.is_symlink() or not source.is_file():
            continue

        group = int(source.stem) // 1000
        destination = root / "problems" / f"{group:02d}xxx" / source.name
        relative_destination = destination.relative_to(root)

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Destination already exists: {relative_destination}")
            move(str(source), str(destination))
        except OSError as error:
            print(f"{source.name}: {error}", file=sys.stderr)
            exit_code = 1
        else:
            print(f"{source.name} -> {relative_destination}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
