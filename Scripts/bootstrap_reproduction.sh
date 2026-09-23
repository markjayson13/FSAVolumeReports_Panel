#!/usr/bin/env bash
# One-command frozen release reproduction for macOS, Linux, and Windows WSL.
# Installer documentation: https://docs.astral.sh/uv/configuration/installer/
# A versioned URL preserves the reviewed bootstrap and release asset selection.
set -euo pipefail

FSA_RELEASE_TAG="fsa-research-v2-2026-09-22"
FSA_RELEASE_URL="https://github.com/markjayson13/FSAVolumeReports_Panel/releases/download/${FSA_RELEASE_TAG}"
FSA_DOWNLOAD_MANIFEST_SHA256="30b7d018cb5ab3e38070607cf515e11e59cc0b7e2c56fe0012a4ea819667f1d2"
FSA_UV_VERSION="0.12.18"
FSA_PYTHON_VERSION="3.13.0"
FSA_DEST="${FSA_DEST:-${PWD}/FSA-reproduction}"

fail() { printf 'FSA reproduction: %s\n' "$*" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || fail "curl is required."
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) fail "Use macOS, Linux, or Windows WSL with Bash and curl." ;;
esac
[[ ! -L "$FSA_DEST" ]] || fail "Destination must not be a symlink: $FSA_DEST"
[[ ! -e "$FSA_DEST" || -d "$FSA_DEST" ]] || fail "Destination is not a directory: $FSA_DEST"
if [[ -d "$FSA_DEST" ]]; then
  shopt -s nullglob dotglob
  FSA_EXISTING=("$FSA_DEST"/*)
  [[ ${#FSA_EXISTING[@]} -eq 0 ]] || fail "Destination is not empty: $FSA_DEST. Set FSA_DEST to a new directory and retry. Existing work is preserved."
  shopt -u nullglob dotglob
fi
mkdir -p "$FSA_DEST"
FSA_DEST="$(cd "$FSA_DEST" && pwd -P)"
FSA_DOWNLOADS="$FSA_DEST/downloads"
mkdir -p "$FSA_DOWNLOADS" "$FSA_DEST/.tools"
trap 'printf "Reproduction stopped. Files are preserved in %s. Retry with FSA_DEST set to a new directory.\n" "$FSA_DEST" >&2' ERR

printf 'Reproducing %s in %s\n' "$FSA_RELEASE_TAG" "$FSA_DEST"
printf 'Downloading the frozen inputs, canonical panels, metadata, and all export formats.\n'
FSA_ASSETS=(
  SHA256SUMS.txt
  distribution_manifest.json
  download_manifest.json
)
for FSA_ASSET in "${FSA_ASSETS[@]}"; do
  printf '  %s\n' "$FSA_ASSET"
  curl --fail --location --show-error --silent --retry 5 --retry-delay 2 \
    --connect-timeout 30 --output "$FSA_DOWNLOADS/$FSA_ASSET.part" \
    "$FSA_RELEASE_URL/$FSA_ASSET" </dev/null
  mv "$FSA_DOWNLOADS/$FSA_ASSET.part" "$FSA_DOWNLOADS/$FSA_ASSET"
done

# Reuse only the exact pinned uv. Otherwise install locally without changing PATH
# or shell profiles. Python, packages, and caches also stay within FSA_DEST.
FSA_UV=""
uv_version_matches() {
  local FSA_FOUND_UV
  FSA_FOUND_UV="$("$1" --version)"
  [[ "$FSA_FOUND_UV" == "uv ${FSA_UV_VERSION}" || "$FSA_FOUND_UV" == "uv ${FSA_UV_VERSION} "* ]]
}
if command -v uv >/dev/null 2>&1; then
  if uv_version_matches "$(command -v uv)"; then
    FSA_UV="$(command -v uv)"
  fi
fi
if [[ -z "$FSA_UV" ]]; then
  printf 'Installing isolated uv %s.\n' "$FSA_UV_VERSION"
  curl --fail --location --show-error --silent --retry 5 --connect-timeout 30 \
    --output "$FSA_DEST/.tools/install-uv.sh" \
    "https://astral.sh/uv/${FSA_UV_VERSION}/install.sh" </dev/null
  env UV_UNMANAGED_INSTALL="$FSA_DEST/.tools/uv" UV_NO_MODIFY_PATH=1 \
    sh "$FSA_DEST/.tools/install-uv.sh" </dev/null
  FSA_UV="$FSA_DEST/.tools/uv/uv"
fi
uv_version_matches "$FSA_UV" || fail "Unexpected uv version."
export UV_CACHE_DIR="$FSA_DEST/.tools/cache"
export UV_PYTHON_INSTALL_DIR="$FSA_DEST/.tools/python"
export UV_TOOL_DIR="$FSA_DEST/.tools/tools"
export UV_TOOL_BIN_DIR="$FSA_DEST/.tools/bin"
export UV_NO_MODIFY_PATH=1
export UV_NO_PROGRESS=1
printf 'Creating isolated Python %s environment.\n' "$FSA_PYTHON_VERSION"
"$FSA_UV" --no-config venv --python "$FSA_PYTHON_VERSION" --managed-python "$FSA_DEST/.venv" </dev/null
FSA_PYTHON="$FSA_DEST/.venv/bin/python"

# Release pieces reconstruct the original, byte-identical archives. Authenticate
# the entire download plan before using any names, sizes, or hashes from it.
"$FSA_PYTHON" - "$FSA_DOWNLOADS" "$FSA_DOWNLOAD_MANIFEST_SHA256" <<'PY_DOWNLOAD'
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RELEASE_TAG = "fsa-research-v2-2026-09-22"
RELEASE_URL = "https://github.com/markjayson13/FSAVolumeReports_Panel/releases/download/" + RELEASE_TAG
ARCHIVES = {
    "fsa-research-v2-replication.zip",
    "fsa-research-v2-canonical.zip",
    "fsa-research-v2-portable-data.zip",
    "fsa-research-v2-stata.zip",
    "fsa-research-v2-excel.zip",
}
STATA = "fsa-research-v2-stata.zip"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate download manifest field: {key}")
        result[key] = value
    return result


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Unexpected download manifest fields")


def content_record(record):
    if type(record["bytes"]) is not int or record["bytes"] <= 0:
        raise ValueError("Download lengths must be positive integers")
    if not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise ValueError("Malformed download SHA256")


def validate_manifest(path, expected_digest):
    if sha256(path) != expected_digest:
        raise ValueError("Pinned download manifest SHA256 verification failed")
    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    fields(manifest, {"schema_version", "release_tag", "archives"})
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported download manifest schema")
    if manifest["release_tag"] != RELEASE_TAG:
        raise ValueError("Unexpected download release tag")
    archives = manifest["archives"]
    if not isinstance(archives, list) or len(archives) != len(ARCHIVES):
        raise ValueError("Download archive inventory differs from the expected release")
    seen = set()
    for archive in archives:
        fields(archive, {"name", "bytes", "sha256", "parts"})
        name = archive["name"]
        if not isinstance(name, str) or name not in ARCHIVES or name in seen:
            raise ValueError("Download archive inventory differs from the expected release")
        seen.add(name)
        content_record(archive)
        parts = archive["parts"]
        if not isinstance(parts, list) or not 1 <= len(parts) <= 9999:
            raise ValueError("Invalid download part inventory")
        if name == STATA and len(parts) != 1:
            raise ValueError("Stata requires its single original archive asset")
        for index, part in enumerate(parts, 1):
            fields(part, {"name", "bytes", "sha256"})
            expected_name = name if name == STATA else f"{name}.part{index:04d}"
            if part["name"] != expected_name:
                raise ValueError("Unexpected download part name or order")
            content_record(part)
        if sum(part["bytes"] for part in parts) != archive["bytes"]:
            raise ValueError("Download part lengths do not sum to archive length")
        if name == STATA and parts[0]["sha256"] != archive["sha256"]:
            raise ValueError("Stata asset and archive hashes differ")
    return archives


def verify_file(path, record):
    if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
        raise ValueError(f"Download length or SHA256 verification failed: {record['name']}")


def download_archives(downloads, archives):
    for archive in archives:
        print(f"Downloading {archive['name']} ({len(archive['parts'])} parts)", flush=True)
        pieces = []
        for index, part in enumerate(archive["parts"], 1):
            print(f"  Part {index}/{len(archive['parts'])}: {part['name']}", flush=True)
            target = downloads / part["name"]
            temporary = downloads / (part["name"] + ".download")
            whole_archive = part["name"] == archive["name"]
            subprocess.run([
                "curl", "--fail", "--location", "--show-error", "--silent",
                "--retry", "5", "--retry-delay", "2", "--retry-max-time", "3600" if whole_archive else "600",
                "--connect-timeout", "30", "--max-time", "1800" if whole_archive else "300",
                "--output", str(temporary), RELEASE_URL + "/" + part["name"],
            ], check=True, stdin=subprocess.DEVNULL)
            verify_file(temporary, part)
            temporary.rename(target)
            pieces.append(target)
        target = downloads / archive["name"]
        if archive["name"] != STATA:
            temporary = downloads / (archive["name"] + ".assembling")
            with temporary.open("xb") as sink:
                for piece in pieces:
                    with piece.open("rb") as source:
                        shutil.copyfileobj(source, sink, length=1024 * 1024)
            verify_file(temporary, archive)
            temporary.rename(target)
            for piece in pieces:
                piece.unlink()
        else:
            verify_file(target, archive)
        print(f"Verified original archive: {archive['name']}", flush=True)


def main():
    downloads = Path(sys.argv[1])
    archives = validate_manifest(downloads / "download_manifest.json", sys.argv[2])
    download_archives(downloads, archives)


if __name__ == "__main__":
    main()
PY_DOWNLOAD

# Verify every downloaded asset before reading its metadata or extracting it.
"$FSA_PYTHON" - "$FSA_DEST" <<'PY_VERIFY'
import hashlib
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

ASSET_ROOTS = {
    "fsa-research-v2-replication.zip": "replication",
    "fsa-research-v2-canonical.zip": "canonical",
    "fsa-research-v2-portable-data.zip": "unitid",
    "fsa-research-v2-stata.zip": "unitid",
    "fsa-research-v2-excel.zip": "unitid",
}
EXPECTED = set(ASSET_ROOTS) | {"distribution_manifest.json"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(downloads):
    hashes = {}
    for line in (downloads / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^/\\]+)", line)
        if not match:
            raise ValueError("Malformed SHA256SUMS entry")
        digest, name = match.groups()
        if name in hashes:
            raise ValueError(f"Duplicate checksum entry: {name}")
        hashes[name] = digest.lower()
    if set(hashes) != EXPECTED:
        raise ValueError("Checksum inventory differs from the expected release assets")
    for name in sorted(EXPECTED):
        path = downloads / name
        if not path.is_file() or sha256(path) != hashes[name]:
            raise ValueError(f"SHA256 verification failed: {name}")
    print("All release assets passed SHA256 verification.", flush=True)


def safe_extract(archive_path, destination, expected_root):
    destination = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        members = []
        # Reject unsafe entries before writing anything from this archive.
        for info in archive.infolist():
            name = info.filename
            relative = PurePosixPath(name)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if (not name or "\\" in name or ":" in name or relative.is_absolute()
                    or ".." in relative.parts or relative.parts[0] != expected_root
                    or kind not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"Unsafe archive member: {name!r}")
            if relative in seen:
                raise ValueError(f"Duplicate archive member: {name!r}")
            seen.add(relative)
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError(f"Archive member escapes destination: {name!r}")
            members.append((info, target))
        for info, target in members:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                # Shared export metadata is permitted only when byte-identical.
                with archive.open(info) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if not target.is_file() or sha256(target) != digest:
                    raise ValueError(f"Conflicting archive member: {info.filename!r}")
                continue
            with archive.open(info) as source, target.open("xb") as sink:
                shutil.copyfileobj(source, sink)


def main():
    destination = Path(sys.argv[1])
    downloads = destination / "downloads"
    verify_assets(downloads)
    for name, root in ASSET_ROOTS.items():
        print(f"Extracting {name}", flush=True)
        safe_extract(downloads / name, destination, root)


if __name__ == "__main__":
    main()
PY_VERIFY

# The frozen runner checks the actual interpreter and all manifest dependency
# versions again before executing any build stages.
printf 'Installing the frozen release dependency versions.\n'
"$FSA_UV" --no-config pip install --python "$FSA_PYTHON" \
  --index-url https://pypi.org/simple \
  --requirement "$FSA_DEST/replication/environment-requirements.txt" \
  --requirement "$FSA_DEST/replication/environment-lock.txt" </dev/null
printf 'Rebuilding from the frozen local sources and comparing against the canonical release.\n'
"$FSA_PYTHON" "$FSA_DEST/replication/reproduce_frozen_release.py" \
  --bundle "$FSA_DEST/replication" \
  --output "$FSA_DEST/rebuilt" \
  --reference-root "$FSA_DEST/canonical" </dev/null
printf '\nReproduction completed successfully.\n'
printf 'Rebuilt panels and validation: %s/rebuilt\n' "$FSA_DEST"
printf 'Labeled Stata, CSV, Excel, Parquet and metadata: %s/unitid\n' "$FSA_DEST"
printf 'Canonical reference panels: %s/canonical\n' "$FSA_DEST"
printf 'Frozen source and input manifests: %s/replication\n' "$FSA_DEST"
