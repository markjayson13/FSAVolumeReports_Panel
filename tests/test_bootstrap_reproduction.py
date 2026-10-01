"""Local frozen bootstrap does not silently select mixed remote release assets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'Scripts/bootstrap_reproduction.sh'


class BootstrapTests(unittest.TestCase):
    def test_offline_interpreter_preserves_paths_with_spaces_and_runner_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / 'bundle with spaces'
            bundle.mkdir()
            (bundle / 'input_manifest.json').write_text('{}')
            (bundle / 'reproduce_frozen_release.py').write_text('import json,sys; print(json.dumps(sys.argv[1:]))')
            output = root / 'new output'
            result = subprocess.run(['bash', str(SCRIPT), str(bundle), str(output), '--reference-root', str(root / 'reference')],
                env={**os.environ, 'FSA_PYTHON': sys.executable}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['--bundle', str(bundle.resolve()), '--output', str(output), '--reference-root', str(root / 'reference')])
            self.assertFalse((root / 'new output.runtime').exists())

    def test_existing_output_is_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'input_manifest.json').write_text('{}')
            (root / 'reproduce_frozen_release.py').write_text('raise AssertionError("should never execute")')
            result = subprocess.run(['bash', str(SCRIPT), str(root), str(root)],
                env={**os.environ, 'FSA_PYTHON': sys.executable}, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('must not already exist', result.stderr)

    def test_missing_arguments_are_actionable(self):
        result = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage:', result.stderr)

    def test_overlapping_paths_are_rejected_without_mutating_frozen_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / 'bundle'
            inputs = bundle / 'inputs/fsa'
            inputs.mkdir(parents=True)
            (bundle / 'input_manifest.json').write_text('{}')
            (bundle / 'reproduce_frozen_release.py').write_text('raise AssertionError("must not execute")')
            (inputs / 'frozen.xls').write_bytes(b'original workbook bytes')
            alias = root / 'alias-to-inputs'
            alias.symlink_to(inputs, target_is_directory=True)
            initial = {str(p.relative_to(bundle)): p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
            initial_entries = sorted(str(p.relative_to(bundle)) for p in bundle.rglob('*'))
            cases = [
                (inputs / 'rebuilt', None),
                (root / 'output', inputs / 'runtime'),
                (root / 'output', root),
                (alias / 'rebuilt', None),
                (root / 'output', alias / 'runtime'),
                (root / 'output', root / 'output/runtime'),
            ]
            for output, runtime in cases:
                with self.subTest(output=output, runtime=runtime):
                    env = {k: v for k, v in os.environ.items() if k not in {'FSA_PYTHON', 'FSA_RUNTIME'}}
                    if runtime is not None:
                        env['FSA_RUNTIME'] = str(runtime)
                    result = subprocess.run(['bash', str(SCRIPT), str(bundle), str(output)],
                                            env=env, capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('must be separate directory trees', result.stderr)
                    self.assertFalse(output.exists())
                    self.assertEqual(sorted(str(p.relative_to(bundle)) for p in bundle.rglob('*')), initial_entries)
                    self.assertEqual({str(p.relative_to(bundle)): p.read_bytes() for p in bundle.rglob('*') if p.is_file()}, initial)
                    if runtime is None:
                        self.assertFalse(Path(str(output) + '.runtime').exists())
                    elif runtime != root:
                        self.assertFalse(runtime.exists())
