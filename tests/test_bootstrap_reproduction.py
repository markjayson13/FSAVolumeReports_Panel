"""Exercise release download integrity and safe extraction without network access."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "Scripts" / "bootstrap_reproduction.sh"
SOURCE = SCRIPT.read_text(encoding="utf-8")
VERIFY_CODE = SOURCE.split("<<'PY_VERIFY'\n", 1)[1].split("\nPY_VERIFY\n", 1)[0]
VERIFY = {"__name__": "bootstrap_verification_test"}
exec(compile(VERIFY_CODE, str(SCRIPT) + ":PY_VERIFY", "exec"), VERIFY)


class BootstrapReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fsa-bootstrap-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, entries):
        path = self.root / "test.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in entries:
                archive.writestr(name, value)
        return path

    def extract(self, path, target=None):
        target = target or self.root / "out"
        VERIFY["safe_extract"](path, target, "replication")
        return target

    def checksum_fixture(self):
        hashes = []
        for name in sorted(VERIFY["EXPECTED"]):
            payload = name.encode("ascii")
            (self.root / name).write_bytes(payload)
            hashes.append(hashlib.sha256(payload).hexdigest() + "  " + name)
        (self.root / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n")

    def mocked_bootstrap(self, corrupt=False):
        """Run the real shell orchestration with local release/download fixtures."""
        assets = self.root / "assets"
        assets.mkdir()
        runner = (
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser()\n"
            "for option in ('bundle','output','reference-root'): p.add_argument('--'+option,required=True)\n"
            "a=p.parse_args()\n"
            "assert (Path(a.reference_root)/'panel.txt').read_text()=='canonical'\n"
            "assert (Path(a.bundle)/'environment-lock.txt').exists()\n"
            "Path(a.output).mkdir()\n"
            "(Path(a.output)/'mock-runner-finished').write_text('yes')\n"
        )
        for name, root in VERIFY["ASSET_ROOTS"].items():
            with zipfile.ZipFile(assets / name, "w") as archive:
                if root == "replication":
                    archive.writestr("replication/reproduce_frozen_release.py", runner)
                    archive.writestr("replication/environment-requirements.txt", "")
                    archive.writestr("replication/environment-lock.txt", "")
                elif root == "canonical":
                    archive.writestr("canonical/panel.txt", "canonical")
                else:
                    archive.writestr("unitid/shared-metadata.txt", "same bytes")
                    archive.writestr("unitid/" + name + ".txt", "format")
        (assets / "distribution_manifest.json").write_text("{}")
        (assets / "SHA256SUMS.txt").write_text("".join(
            VERIFY["sha256"](assets / name) + "  " + name + "\n"
            for name in sorted(VERIFY["EXPECTED"])
        ))
        if corrupt:
            (assets / "fsa-research-v2-excel.zip").write_bytes(b"corrupt")
        tools = self.root / "mock-tools"
        tools.mkdir()
        curl = tools / "curl"
        curl.write_text(
            f"#!{sys.executable}\n"
            "import shutil,sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            f"shutil.copyfile(Path({str(assets)!r})/args[-1].rsplit('/',1)[1],args[args.index('--output')+1])\n"
        )
        uv = tools / "uv"
        uv.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "from pathlib import Path\n"
            "a=sys.argv[1:]\n"
            "if a==['--version']: print('uv 0.12.18');sys.exit(0)\n"
            "if 'venv' in a:\n"
            " assert '--managed-python' in a and a[a.index('--python')+1]=='3.13.0'\n"
            " target=Path(a[-1])/'bin';target.mkdir(parents=True)\n"
            f" (target/'python').symlink_to({sys.executable!r})\n"
            "elif 'pip' in a:\n"
            " assert sum(x=='--requirement' for x in a)==2\n"
            "else: raise ValueError(a)\n"
        )
        curl.chmod(0o755)
        uv.chmod(0o755)
        destination = self.root / "fresh destination"
        result = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True,
            env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ.get("PATH", ""),
                 "FSA_DEST": str(destination)},
        )
        return result, destination

    def test_shell_download_install_extract_and_runner_orchestration(self):
        result, destination = self.mocked_bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Reproduction completed successfully", result.stdout)
        self.assertTrue((destination / "rebuilt/mock-runner-finished").is_file())
        self.assertEqual((destination / "unitid/shared-metadata.txt").read_text(), "same bytes")
        self.assertEqual(len(list((destination / "downloads").iterdir())), 7)

    def test_shell_aborts_on_bad_asset_before_any_extraction_or_runner(self):
        result, destination = self.mocked_bootstrap(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 verification failed", result.stderr)
        for name in ("replication", "canonical", "unitid", "rebuilt"):
            self.assertFalse((destination / name).exists())

    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True, capture_output=True)

    def test_refuses_existing_data_before_downloading(self):
        target = self.root / "existing"
        target.mkdir()
        retained = target / ".important"
        retained.write_text("preserve me")
        result = subprocess.run(
            ["bash", str(SCRIPT)], env={**os.environ, "FSA_DEST": str(target)},
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Destination is not empty", result.stderr)
        self.assertEqual(retained.read_text(), "preserve me")
        self.assertEqual(list(target.iterdir()), [retained])

    def test_refuses_symlink_destination(self):
        target = self.root / "link"
        real = self.root / "real"
        real.mkdir()
        target.symlink_to(real, target_is_directory=True)
        result = subprocess.run(
            ["bash", str(SCRIPT)], env={**os.environ, "FSA_DEST": str(target)},
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not be a symlink", result.stderr)
        self.assertFalse(list(real.iterdir()))

    def test_valid_checksums_and_corrupted_asset(self):
        self.checksum_fixture()
        with contextlib.redirect_stdout(io.StringIO()):
            VERIFY["verify_assets"](self.root)
        asset = next(iter(VERIFY["EXPECTED"]))
        (self.root / asset).write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "SHA256 verification failed"):
            VERIFY["verify_assets"](self.root)

    def test_checksum_inventory_is_closed_and_unique(self):
        self.checksum_fixture()
        checksums = self.root / "SHA256SUMS.txt"
        original = checksums.read_text()
        checksums.write_text(original + original.splitlines()[0] + "\n")
        with self.assertRaisesRegex(ValueError, "Duplicate checksum"):
            VERIFY["verify_assets"](self.root)
        checksums.write_text("\n".join(original.splitlines()[1:]) + "\n")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            VERIFY["verify_assets"](self.root)

    def test_checksum_paths_are_rejected(self):
        (self.root / "SHA256SUMS.txt").write_text("a" * 64 + "  ../outside\n")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            VERIFY["verify_assets"](self.root)

    def test_safe_extraction_and_identical_shared_metadata(self):
        archive = self.archive([("replication/", b""), ("replication/readme.txt", b"data")])
        target = self.extract(archive)
        self.extract(archive, target)
        self.assertEqual((target / "replication/readme.txt").read_bytes(), b"data")

    def test_conflicting_metadata_is_not_overwritten(self):
        target = self.extract(self.archive([("replication/readme.txt", b"original")]))
        archive = self.archive([("replication/readme.txt", b"replacement")])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.extract(archive, target)
        self.assertEqual((target / "replication/readme.txt").read_bytes(), b"original")

    def test_all_paths_validated_before_archive_is_written(self):
        for unsafe in ("replication/../../outside", "/replication/absolute", "unexpected/file", "replication\\file", "C:/replication/file"):
            with self.subTest(unsafe=unsafe):
                archive = self.archive([("replication/good", b"good"), (unsafe, b"bad")])
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    self.extract(archive)
                self.assertFalse((self.root / "out").exists())

    def test_archive_symlinks_are_rejected(self):
        info = zipfile.ZipInfo("replication/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.extract(self.archive([(info, b"../../outside")]))

    def test_existing_symlink_parent_cannot_escape_destination(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = self.root / "out"
        (target / "replication").mkdir(parents=True)
        (target / "replication/link").symlink_to(outside, target_is_directory=True)
        archive = self.archive([("replication/link/file", b"bad")])
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.extract(archive, target)
        self.assertFalse(list(outside.iterdir()))

    def test_duplicate_archive_members_are_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            archive = self.archive([("replication/file", b"one"), ("replication/file", b"two")])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.extract(archive)


if __name__ == "__main__":
    unittest.main()
