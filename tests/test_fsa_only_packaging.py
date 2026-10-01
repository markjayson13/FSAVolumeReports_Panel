"""Separation preserves source provenance and excludes downstream artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from helpers import load_script_module
import fsa_release_integrity
import reproduce_frozen_release

packager = load_script_module('fsa_only_packager', 'Scripts/package_public_release.py')


class FSAOnlyPackagingTests(unittest.TestCase):
    def fixture(self, root):
        build = root / 'build'
        snapshot = build / 'source_snapshot'
        sources = {
            'Scripts/00_run_all.py': b'# frozen pipeline',
            'Scripts/reproduce_frozen_release.py': b'# frozen runner',
            'requirements.txt': b'pandas',
            'Metadata/reproduction_environment.txt': b'pandas==2.2.3',
        }
        for name, data in sources.items():
            p = snapshot / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        raw = root / 'Raw_Title_IV_Reports/Grant_Volume/2000/downloads/example.xls'
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b'workbook bytes')
        row = {'family': 'grants', 'award_year': '2000-2001', 'filename': raw.name,
               'local_path': str(raw), 'selected_for_panel': 'True', 'sha256': packager.digest(raw),
               'filesize_bytes': str(raw.stat().st_size)}
        reproduce_frozen_release.write_csv(root / 'Checks/download_qc/selected_panel_files.csv', list(row), [row])
        release = {'repository_scope': 'fsa_reporting_unit_panel', 'acceptance_passed': True,
                   'inputs': [{**row, 'verified_sha256': packager.digest(raw)}],
                   'code_and_metadata': [{'path': p, 'sha256': packager.digest(snapshot / p)} for p in sources],
                   'environment': {}, 'artifacts': []}
        (build / 'research_release_manifest.json').write_text(json.dumps(release))
        (build / 'environment-requirements.txt').write_text('pandas==2.2.3')
        downstream = root / 'Panels/ipeds/bridge.parquet'
        downstream.parent.mkdir(parents=True)
        downstream.write_bytes(b'unrelated downstream output')
        # Historical source snapshots can have stale files; archive only recorded code.
        (snapshot / 'Scripts/13_link_ipeds.py').write_text('# old linkage code')
        return release

    @patch.object(fsa_release_integrity, 'require_current_qa')
    def test_package_verifies_as_fsa_only_and_excludes_downstream_artifacts(self, qa):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fsa'
            self.fixture(root)
            out = Path(tmp) / 'distribution'
            result = packager.package(root, out)
            self.assertEqual(len(result['assets']), 2)
            self.assertFalse(result['published'])
            original, records = reproduce_frozen_release.verify_bundle(out / 'replication')
            self.assertEqual(original['repository_scope'], 'fsa_reporting_unit_panel')
            self.assertFalse(any('ipeds' in p for p in records))
            for artifact in result['assets']:
                with zipfile.ZipFile(out / 'assets' / artifact['name']) as archive:
                    self.assertFalse(any('ipeds' in name for name in archive.namelist()))
            qa.assert_called_once_with(root)

    def test_legacy_mixed_release_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fsa'
            release = self.fixture(root)
            release.pop('repository_scope')
            (root / 'build/research_release_manifest.json').write_text(json.dumps(release))
            with self.assertRaisesRegex(ValueError, 'accepted FSA-only'):
                packager.stage(root, Path(tmp) / 'distribution')
