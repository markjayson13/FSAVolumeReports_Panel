#!/usr/bin/env bash
# Reproduce an extracted FSA-only replication bundle; original inputs stay frozen.
set -euo pipefail
if [[ $# -lt 2 ]]; then
  echo "Usage: bash Scripts/bootstrap_reproduction.sh /path/to/replication /path/to/new-output [runner options]" >&2
  exit 2
fi
BUNDLE="$(cd "$1" && pwd -P)"
OUTPUT="$2"
shift 2
[[ -f "$BUNDLE/input_manifest.json" && -f "$BUNDLE/reproduce_frozen_release.py" ]] || { echo "Missing frozen FSA replication bundle" >&2; exit 1; }
[[ ! -e "$OUTPUT" && ! -L "$OUTPUT" ]] || { echo "Output must not already exist" >&2; exit 1; }
# Validate all locations before creating runtime directories or downloading files.
RUNTIME=""
if [[ -z "${FSA_PYTHON:-}" ]]; then
  RUNTIME="${FSA_RUNTIME:-${OUTPUT}.runtime}"
  [[ ! -L "$RUNTIME" ]] || { echo "Runtime must not be a symlink" >&2; exit 1; }
fi
command -v python3 >/dev/null 2>&1 || { echo "python3 is required for read-only path validation" >&2; exit 1; }
python3 - "$BUNDLE" "$OUTPUT" "$RUNTIME" <<'PY_PREFLIGHT'
from pathlib import Path
import sys

locations = [("bundle", Path(sys.argv[1]).resolve()), ("output", Path(sys.argv[2]).resolve())]
if sys.argv[3]:
    locations.append(("runtime", Path(sys.argv[3]).resolve()))
for index, (left_name, left) in enumerate(locations):
    for right_name, right in locations[index + 1:]:
        if left == right or left in right.parents or right in left.parents:
            raise SystemExit(f"{left_name} and {right_name} must be separate directory trees")
PY_PREFLIGHT
# An explicit interpreter makes offline reuse possible; no shell profile changes.
if [[ -n "${FSA_PYTHON:-}" ]]; then
  PYTHON="$FSA_PYTHON"
else
  mkdir -p "$RUNTIME"
  RUNTIME="$(cd "$RUNTIME" && pwd -P)"
  UV="$RUNTIME/uv/uv"
  if [[ ! -x "$UV" ]]; then
    curl -fsSL --retry 5 https://astral.sh/uv/0.12.18/install.sh -o "$RUNTIME/install-uv.sh"
    env UV_UNMANAGED_INSTALL="$RUNTIME/uv" UV_NO_MODIFY_PATH=1 sh "$RUNTIME/install-uv.sh" </dev/null
  fi
  [[ "$("$UV" --version)" == "uv 0.12.18"* ]] || { echo "Unexpected uv version" >&2; exit 1; }
  export UV_CACHE_DIR="$RUNTIME/cache" UV_PYTHON_INSTALL_DIR="$RUNTIME/python" UV_NO_MODIFY_PATH=1
  if [[ ! -x "$RUNTIME/.venv/bin/python" ]]; then
    "$UV" --no-config venv --python 3.13.0 --managed-python "$RUNTIME/.venv" </dev/null
  fi
  PYTHON="$RUNTIME/.venv/bin/python"
  "$UV" --no-config pip install --python "$PYTHON" --index-url https://pypi.org/simple -r "$BUNDLE/environment-lock.txt" </dev/null
fi
exec "$PYTHON" "$BUNDLE/reproduce_frozen_release.py" --bundle "$BUNDLE" --output "$OUTPUT" "$@"
