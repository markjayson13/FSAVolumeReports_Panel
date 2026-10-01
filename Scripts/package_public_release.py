#!/usr/bin/env python3
"""Package an accepted FSA-only release and frozen reproduction inputs locally.

This writes assets; it never publishes them. Legacy mixed releases retain their
original runner and manifests at their immutable Git tag.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TAG = 'fsa-research-v3-fsa-only'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def files(root):
    return sorted(p for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink()
                  and not any(x in {'__pycache__', '.pytest_cache', '.DS_Store'} or x.startswith('._') for x in p.parts)
                  and p.suffix not in {'.pyc', '.pyo'})


def copy(source, target, expected=None):
    if expected and digest(source) != expected:
        raise ValueError(f'Changed input: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if digest(source) != digest(target):
        raise ValueError(f'Copy mismatch: {target}')


def stage(root, distribution):
    from fsa_release_integrity import require_current_qa
    from reproduce_frozen_release import fsa_relative_path, safe_member
    release = json.loads((root / 'build/research_release_manifest.json').read_text())
    if release.get('repository_scope') != 'fsa_reporting_unit_panel' or release.get('acceptance_passed') is not True:
        raise ValueError('Package only an accepted FSA-only release; legacy mixed bundles remain historical')
    require_current_qa(root)
    replication = distribution / 'replication'
    if replication.exists():
        raise ValueError('Replication destination must not exist')
    for item in release['inputs']:
        source = Path(item['local_path'])
        copy(source, replication / 'inputs/fsa' / fsa_relative_path(str(source)), item['verified_sha256'])
    snapshot = root / 'build/source_snapshot'
    for item in release['code_and_metadata']:
        relative = item['path']
        source = safe_member(snapshot, relative)
        copy(source, replication / 'source' / relative, item['sha256'])
    for source, target in (
        (root / 'build/research_release_manifest.json', 'original_release_manifest.json'),
        (root / 'Checks/download_qc/selected_panel_files.csv', 'selected_panel_files.csv'),
        (root / 'build/environment-requirements.txt', 'environment-requirements.txt'),
        (snapshot / 'Metadata/reproduction_environment.txt', 'environment-lock.txt'),
        (snapshot / 'Scripts/reproduce_frozen_release.py', 'reproduce_frozen_release.py'),
    ):
        copy(source, replication / target)
    records = [{'path': str(p.relative_to(replication)), 'bytes': p.stat().st_size, 'sha256': digest(p)}
               for p in files(replication)]
    (replication / 'input_manifest.json').write_text(json.dumps({
        'schema_version': 1, 'release_tag': TAG, 'repository_scope': 'fsa_reporting_unit_panel', 'files': records}, indent=2) + '\n')
    return replication


def archive(path, members):
    if path.exists():
        raise ValueError(f'Archive already exists: {path}')
    names = set()
    with zipfile.ZipFile(path, 'w', allowZip64=True) as z:
        for name, p in sorted(members):
            if name in names:
                raise ValueError(f'Duplicate archive path: {name}')
            names.add(name)
            compression = zipfile.ZIP_STORED if p.suffix in {'.zip', '.gz', '.xlsx', '.parquet', '.pdf'} else zipfile.ZIP_DEFLATED
            z.write(p, name, compress_type=compression, compresslevel=1)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('Archive CRC failure')
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path), 'members': len(names)}


def package(root, distribution):
    replication = stage(root, distribution)
    assets = distribution / 'assets'
    assets.mkdir()
    canonical = []
    for folder in ('Panels', 'Dictionary', 'Checks', 'Cross_sections', 'build'):
        for p in files(root / folder):
            relative = p.relative_to(root)
            if 'ipeds' not in relative.parts and not relative.is_relative_to('build/source_snapshot'):
                canonical.append(('canonical/' + str(relative), p))
    release = json.loads((root / 'build/research_release_manifest.json').read_text())
    for item in release['code_and_metadata']:
        p = root / 'build/source_snapshot' / item['path']
        canonical.append(('canonical/' + str(p.relative_to(root)), p))
    records = [archive(assets / f'{TAG}-canonical.zip', canonical),
               archive(assets / f'{TAG}-replication.zip', [('replication/' + str(p.relative_to(replication)), p) for p in files(replication)])]
    manifest = {'schema_version': 1, 'release_tag': TAG, 'repository': 'markjayson13/FSAVolumeReports_Panel',
                'repository_scope': 'fsa_reporting_unit_panel', 'assets': records,
                'source_release_manifest_sha256': digest(root / 'build/research_release_manifest.json'),
                'scope': 'FSA OPEID-by-award-year master, FSA inputs, dictionaries, evidence and frozen source.',
                'published': False,
                'historical_paths': 'Absolute paths are provenance; input_manifest.json uses portable relative paths.'}
    path = assets / 'distribution_manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    sums = [f"{r['sha256']}  {r['name']}" for r in records] + [f'{digest(path)}  distribution_manifest.json']
    (assets / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--distribution', type=Path, required=True)
    parser.add_argument('--stage-only', action='store_true')
    args = parser.parse_args()
    args.distribution.mkdir(parents=True, exist_ok=True)
    print(stage(args.root.resolve(), args.distribution.resolve()) if args.stage_only else
          json.dumps(package(args.root.resolve(), args.distribution.resolve()), indent=2))
