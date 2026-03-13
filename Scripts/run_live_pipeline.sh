#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash Scripts/run_live_pipeline.sh [options]

Options:
  --root PATH          External FSA_ROOT. Defaults to /Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling
  --venv PATH          Virtualenv path. Defaults to .venv in the repo root.
  --python CMD         Python interpreter used to create the venv. Defaults to python3.
  --page-html PATH     Optional local HTML or JSON fixture for stage 01 discovery.
  --preflight-only     Stop after the strict source preflight.
  --skip-install       Reuse the current venv without reinstalling dependencies.
  --skip-tests         Skip the local unittest smoke test before the live run.
  --skip-qaqc          Skip QA/QC stages during the full pipeline run.
  -h, --help           Show this message.

Examples:
  bash Scripts/run_live_pipeline.sh
  bash Scripts/run_live_pipeline.sh --preflight-only
  bash Scripts/run_live_pipeline.sh --root /path/to/FSA_ROOT --skip-install
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_FSA_ROOT="/Users/markjaysonfarol13/Projects/FSAVolumeReports_Paneling"
FSA_ROOT="${FSA_ROOT:-$DEFAULT_FSA_ROOT}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
PYTHON_CMD="${PYTHON_CMD:-python3}"
PAGE_HTML=""
PREFLIGHT_ONLY=0
SKIP_INSTALL=0
SKIP_TESTS=0
SKIP_QAQC=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      FSA_ROOT="$2"
      shift 2
      ;;
    --venv)
      VENV_DIR="$2"
      shift 2
      ;;
    --python)
      PYTHON_CMD="$2"
      shift 2
      ;;
    --page-html)
      PAGE_HTML="$2"
      shift 2
      ;;
    --preflight-only)
      PREFLIGHT_ONLY=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-qaqc)
      SKIP_QAQC=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_CMD" >&2
  exit 1
fi

mkdir -p "$(dirname "$VENV_DIR")"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[setup] creating virtualenv at $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [[ ! -x "$VENV_PYTHON" || ! -x "$VENV_PIP" ]]; then
  echo "Virtualenv is missing python or pip: $VENV_DIR" >&2
  exit 1
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "[setup] upgrading pip tooling"
  "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
  echo "[setup] installing repo requirements"
  "$VENV_PIP" install -r "$REPO_ROOT/requirements.txt"
fi

export FSA_ROOT

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  echo "[check] running repo unittest suite"
  "$VENV_PYTHON" -m unittest discover -s "$REPO_ROOT/tests" -v
fi

PREFLIGHT_CMD=(
  "$VENV_PYTHON"
  "$REPO_ROOT/Scripts/01_download_title_iv_reports.py"
  "--root" "$FSA_ROOT"
  "--verify-only"
)

if [[ -n "$PAGE_HTML" ]]; then
  PREFLIGHT_CMD+=("--page-html" "$PAGE_HTML")
fi

echo "[run] strict source preflight"
"${PREFLIGHT_CMD[@]}"

echo "[info] preflight artifacts"
echo "  $FSA_ROOT/Checks/download_qc/preflight_release_inventory.csv"
echo "  $FSA_ROOT/Checks/download_qc/preflight_selected_panel_files.csv"
echo "  $FSA_ROOT/Checks/download_qc/preflight_inventory_summary.csv"
echo "  $FSA_ROOT/Checks/download_qc/preflight_validation.csv"

if [[ "$PREFLIGHT_ONLY" -eq 1 ]]; then
  echo "[done] preflight completed; full run skipped"
  exit 0
fi

RUN_CMD=(
  "$VENV_PYTHON"
  "$REPO_ROOT/Scripts/00_run_all.py"
  "--root" "$FSA_ROOT"
  "--skip-preflight"
)

if [[ -n "$PAGE_HTML" ]]; then
  RUN_CMD+=("--page-html" "$PAGE_HTML")
fi

if [[ "$SKIP_QAQC" -eq 0 ]]; then
  RUN_CMD+=("--run-qaqc")
fi

echo "[run] full pipeline"
"${RUN_CMD[@]}"

echo "[done] pipeline completed"
echo "  final raw panel:   $FSA_ROOT/Panels/final/fsa_volume_reports_raw_1999_2025.parquet"
echo "  final clean panel: $FSA_ROOT/Panels/final/fsa_volume_reports_clean_1999_2025.parquet"
