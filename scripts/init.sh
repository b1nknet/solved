#!/usr/bin/env bash
set -e

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
python3 "$script_dir/organize_problems.py"
exec python3 "$script_dir/update_readme.py"
