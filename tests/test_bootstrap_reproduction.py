"""Exercise release download integrity and safe extraction without network access."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
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
DOWNLOAD_CODE = SOURCE.split("<<'PY_DOWNLOAD'\n", 1)[1].split("\nPY_DOWNLOAD\n", 1)[0]
DOWNLOAD = {"__name__": "bootstrap_download_test"}
exec(compile(DOWNLOAD_CODE, str(SCRIPT) + ":PY_DOWNLOAD", "exec"), DOWNLOAD)


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

    def mocked_bootstrap(self, mutate_manifest=None, mutate_assets=None, tamper_manifest=False):
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
        manifest = {"schema_version": 1, "release_tag": DOWNLOAD["RELEASE_TAG"], "archives": []}
        for name in VERIFY["ASSET_ROOTS"]:
            payload = (assets / name).read_bytes()
            entry = {"name": name, "bytes": len(payload),
                     "sha256": hashlib.sha256(payload).hexdigest(), "parts": []}
            if name == DOWNLOAD["STATA"]:
                entry["parts"].append({key: entry[key] for key in ("name", "bytes", "sha256")})
            else:
                midpoint = len(payload) // 2
                for index, part in enumerate((payload[:midpoint], payload[midpoint:]), 1):
                    part_name = f"{name}.part{index:04d}"
                    (assets / part_name).write_bytes(part)
                    entry["parts"].append({"name": part_name, "bytes": len(part),
                                           "sha256": hashlib.sha256(part).hexdigest()})
            manifest["archives"].append(entry)
        if mutate_manifest:
            mutate_manifest(manifest)
        manifest_path = assets / "download_manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        # Fixtures replace only the compile-time digest; there is no runtime bypass.
        fixture_source, substitutions = re.subn(
            r'FSA_DOWNLOAD_MANIFEST_SHA256="[0-9a-f]{64}"',
            f'FSA_DOWNLOAD_MANIFEST_SHA256="{VERIFY["sha256"](manifest_path)}"', SOURCE,
        )
        self.assertEqual(substitutions, 1)
        fixture_script = self.root / "bootstrap.sh"
        fixture_script.write_text(fixture_source)
        if tamper_manifest:
            manifest_path.write_text(manifest_path.read_text() + " ")
        if mutate_assets:
            mutate_assets(assets, manifest)
        tools = self.root / "mock-tools"
        tools.mkdir()
        curl = tools / "curl"
        curl.write_text(
            f"#!{sys.executable}\n"
            "import shutil,sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "name=args[-1].rsplit('/',1)[1]\n"
            "if '.zip' in name:\n"
            " whole=name.endswith('.zip')\n"
            " assert args[args.index('--max-time')+1]==('1800' if whole else '300')\n"
            " assert args[args.index('--retry-max-time')+1]==('3600' if whole else '600')\n"
            " assert args[args.index('--retry')+1]=='5'\n"
            f"with Path({str(self.root / 'curl-requests.txt')!r}).open('a') as log: log.write(args[-1]+'\\n')\n"
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
            ["bash", str(fixture_script)], capture_output=True, text=True,
            env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ.get("PATH", ""),
                 "FSA_DEST": str(destination)},
        )
        return result, destination

    def test_shell_download_install_extract_and_runner_orchestration(self):
        result, destination = self.mocked_bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Reproduction completed successfully", result.stdout)
        self.assertIn("Part 1/1: fsa-research-v2-stata.zip", result.stdout)
        self.assertIn("Part 2/2: fsa-research-v2-canonical.zip.part0002", result.stdout)
        self.assertTrue((destination / "rebuilt/mock-runner-finished").is_file())
        self.assertEqual((destination / "unitid/shared-metadata.txt").read_text(), "same bytes")
        self.assertEqual(len(list((destination / "downloads").iterdir())), 8)
        for name in VERIFY["ASSET_ROOTS"]:
            self.assertEqual((destination / "downloads" / name).read_bytes(),
                             (self.root / "assets" / name).read_bytes())
        requests = (self.root / "curl-requests.txt").read_text().splitlines()
        self.assertEqual(len(requests), 12)  # Three metadata, eight pieces, one whole Stata.
        self.assertFalse(list((destination / "downloads").glob("*.part*")))

    def test_shell_aborts_on_bad_asset_before_any_extraction_or_runner(self):
        def corrupt(assets, manifest):
            part = manifest["archives"][0]["parts"][0]
            (assets / part["name"]).write_bytes(b"x" * part["bytes"])
        result, destination = self.mocked_bootstrap(mutate_assets=corrupt)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 verification failed", result.stderr)
        self.assert_no_extraction(destination)

    def assert_no_extraction(self, destination):
        for name in ("replication", "canonical", "unitid", "rebuilt"):
            self.assertFalse((destination / name).exists())

    def assert_only_metadata_requested(self):
        self.assertEqual(len((self.root / "curl-requests.txt").read_text().splitlines()), 3)

    def test_shell_aborts_on_missing_part_before_extraction_or_runner(self):
        def missing(assets, manifest):
            (assets / manifest["archives"][0]["parts"][0]["name"]).unlink()
        result, destination = self.mocked_bootstrap(mutate_assets=missing)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CalledProcessError", result.stderr)
        self.assert_no_extraction(destination)

    def test_shell_rejects_reordered_parts_before_downloading_archives(self):
        result, destination = self.mocked_bootstrap(
            mutate_manifest=lambda m: m["archives"][0]["parts"].reverse())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("part name or order", result.stderr)
        self.assert_only_metadata_requested()
        self.assert_no_extraction(destination)

    def test_shell_rejects_malicious_part_name_before_downloading_archives(self):
        result, destination = self.mocked_bootstrap(mutate_manifest=lambda m:
            m["archives"][0]["parts"][0].update(name="../../outside"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("part name or order", result.stderr)
        self.assert_only_metadata_requested()
        self.assert_no_extraction(destination)

    def test_shell_checks_assembled_hash_even_when_parts_verify(self):
        result, destination = self.mocked_bootstrap(mutate_manifest=lambda m:
            m["archives"][0].update(sha256="0" * 64))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256 verification failed: fsa-research-v2-replication.zip", result.stderr)
        self.assertFalse((destination / "downloads/fsa-research-v2-replication.zip").exists())
        self.assertTrue(list((destination / "downloads").glob("*.part*")))
        self.assert_no_extraction(destination)

    def test_shell_authenticates_manifest_before_downloading_archives(self):
        result, destination = self.mocked_bootstrap(tamper_manifest=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pinned download manifest SHA256 verification failed", result.stderr)
        self.assert_only_metadata_requested()
        self.assert_no_extraction(destination)

    def test_manifest_schema_inventory_lengths_and_hashes_are_strict(self):
        def part_entry(name):
            return {"name": name, "bytes": 1, "sha256": "a" * 64}
        manifest = {"schema_version": 1, "release_tag": DOWNLOAD["RELEASE_TAG"], "archives": [
            {**part_entry(name), "parts": [part_entry(
                name if name == DOWNLOAD["STATA"] else name + ".part0001")]} for name in sorted(DOWNLOAD["ARCHIVES"])
        ]}
        mutations = [
            lambda m: m.update(schema_version=True),
            lambda m: m.update(release_tag="other-release"),
            lambda m: m.update(url="https://example.org"),
            lambda m: m["archives"].pop(),
            lambda m: m["archives"].__setitem__(1, m["archives"][0]),
            lambda m: m["archives"][0].update(bytes=True),
            lambda m: m["archives"][0].update(bytes=2),
            lambda m: m["archives"][0].update(sha256="invalid"),
            lambda m: m["archives"][0].update(parts=[]),
            lambda m: m["archives"][0]["parts"][0].update(bytes=0),
            lambda m: m["archives"][0]["parts"][0].update(sha256="A" * 64),
            lambda m: m["archives"][0]["parts"][0].update(url="https://example.org"),
            lambda m: next(a for a in m["archives"] if a["name"] == DOWNLOAD["STATA"])["parts"][0].update(sha256="b" * 64),
        ]
        path = self.root / "download_manifest.json"
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                modified = json.loads(json.dumps(manifest))
                mutate(modified)
                path.write_text(json.dumps(modified))
                with self.assertRaises(ValueError):
                    DOWNLOAD["validate_manifest"](path, VERIFY["sha256"](path))
        path.write_text(json.dumps(manifest).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
        with self.assertRaisesRegex(ValueError, "Duplicate download manifest field"):
            DOWNLOAD["validate_manifest"](path, VERIFY["sha256"](path))

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
