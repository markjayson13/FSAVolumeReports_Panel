#!/usr/bin/env python3
"""Split verified release archives without changing their original bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ARCHIVES = {
    f"fsa-research-v2-{name}.zip"
    for name in ("portable-data", "stata", "excel", "canonical", "replication")
}
WHOLE_ARCHIVE = "fsa-research-v2-stata.zip"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_transport(assets: Path, output: Path, part_bytes: int = 16 * 1024**2) -> dict:
    if not isinstance(part_bytes, int) or isinstance(part_bytes, bool) or part_bytes <= 0:
        raise ValueError("part_bytes must be a positive integer")
    original = json.loads((assets / "distribution_manifest.json").read_text())
    records = original["assets"]
    if len(records) != len(ARCHIVES) or {r["name"] for r in records} != ARCHIVES:
        raise ValueError("Unexpected original archive inventory")
    # Validate all source bytes before producing any new release assets.
    for record in records:
        source = assets / record["name"]
        if source.is_symlink() or source.stat().st_size != record["bytes"] or sha256(source) != record["sha256"]:
            raise ValueError(f"Original archive differs from its manifest: {source.name}")
    output.mkdir(parents=True, exist_ok=True)
    archives = []
    for record in records:
        name = record["name"]
        entry = {key: record[key] for key in ("name", "bytes", "sha256")}
        entry["parts"] = []
        if name == WHOLE_ARCHIVE:
            entry["parts"].append({key: record[key] for key in ("name", "bytes", "sha256")})
        else:
            with (assets / name).open("rb") as source:
                index = 0
                while data := source.read(part_bytes):
                    index += 1
                    part_name = f"{name}.part{index:04d}"
                    target = output / part_name
                    digest = hashlib.sha256(data).hexdigest()
                    if target.exists() or target.is_symlink():
                        if target.is_symlink() or not target.is_file() or target.stat().st_size != len(data) or sha256(target) != digest:
                            raise ValueError(f"Conflicting existing part: {part_name}")
                    else:
                        with target.open("xb") as sink:
                            sink.write(data)
                    entry["parts"].append({"name": part_name, "bytes": len(data), "sha256": digest})
        archives.append(entry)
    manifest = {
        "schema_version": 1,
        "release_tag": original["release_tag"],
        "archives": archives,
    }
    target = output / "download_manifest.json"
    content = (json.dumps(manifest, indent=2) + "\n").encode()
    if target.exists() and target.read_bytes() != content:
        raise ValueError("Existing download manifest differs; use a new output directory")
    if not target.exists():
        with target.open("xb") as sink:
            sink.write(content)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part-bytes", type=int, default=16 * 1024**2)
    arguments = parser.parse_args()
    manifest = package_transport(arguments.assets, arguments.output, arguments.part_bytes)
    print(json.dumps({
        "archive_count": len(manifest["archives"]),
        "download_file_count": sum(len(a["parts"]) for a in manifest["archives"]),
        "download_manifest_sha256": sha256(arguments.output / "download_manifest.json"),
    }, indent=2))
