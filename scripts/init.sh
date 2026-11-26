#!/usr/bin/env bash
set -e

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python=python3
if [[ -x "$script_dir/../.venv/bin/python" ]]; then
    python="$script_dir/../.venv/bin/python"
fi

"$python" "$script_dir/organize_problems.py"
"$python" "$script_dir/update_readme.py"
exec "$python" "$script_dir/generate_streak.py"
