import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import release


class CollectTests(unittest.TestCase):
    def test_collect_merges_valid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw"), Path(tmp, "out")
            (raw / "out-x86_64").mkdir(parents=True)
            (raw / "out-aarch64").mkdir(parents=True)
            (raw / "out-x86_64" / "app-1.0.0-x86_64.tar.gz").write_bytes(b"x86")
            (raw / "out-aarch64" / "app-1.0.0-aarch64.tar.gz").write_bytes(b"arm")

            release.collect(raw, out)

            self.assertEqual(
                sorted(p.name for p in out.iterdir()),
                ["app-1.0.0-aarch64.tar.gz", "app-1.0.0-x86_64.tar.gz"],
            )

    def test_collect_handles_single_flat_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw"), Path(tmp, "out")
            raw.mkdir()
            (raw / "app-1.0.0.tar.gz").write_bytes(b"pkg")

            release.collect(raw, out)

            self.assertEqual([p.name for p in out.iterdir()], ["app-1.0.0.tar.gz"])

    def test_collect_rejects_mixed_files_and_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw"), Path(tmp, "out")
            (raw / "out-a").mkdir(parents=True)
            (raw / "out-a" / "a.tar.gz").write_bytes(b"a")
            (raw / "stray.tar.gz").write_bytes(b"b")

            with self.assertRaises(SystemExit) as ctx:
                release.collect(raw, out)
            self.assertIn("unexpected entry", str(ctx.exception))

    def test_collect_rejects_duplicate_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw"), Path(tmp, "out")
            (raw / "out-a").mkdir(parents=True)
            (raw / "out-b").mkdir(parents=True)
            (raw / "out-a" / "app.tar.gz").write_bytes(b"a")
            (raw / "out-b" / "app.tar.gz").write_bytes(b"b")

            with self.assertRaises(SystemExit) as ctx:
                release.collect(raw, out)
            self.assertIn("duplicate artifact file", str(ctx.exception))

    def test_collect_rejects_symlink_subdir_and_bad_names(self) -> None:
        for case in ("symlink", "subdir", "release.json", "dotfile"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                raw, out = Path(tmp, "raw"), Path(tmp, "out")
                bucket = raw / "out-a"
                bucket.mkdir(parents=True)
                if case == "symlink":
                    target = Path(tmp, "real")
                    target.write_bytes(b"x")
                    (bucket / "link.tgz").symlink_to(target)
                elif case == "subdir":
                    (bucket / "nested").mkdir()
                elif case == "release.json":
                    (bucket / "release.json").write_text("{}")
                elif case == "dotfile":
                    (bucket / ".hidden").write_bytes(b"x")

                with self.assertRaises(SystemExit):
                    release.collect(raw, out)

    def test_collect_rejects_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw"), Path(tmp, "out")
            raw.mkdir()
            with self.assertRaises(SystemExit):
                release.collect(raw, out)


class JsonAndNotesTests(unittest.TestCase):
    def _env(self) -> dict[str, str]:
        return {
            "REPO": "demo",
            "TAG": "v1.2.3",
            "COMMIT": "a" * 64,
            "TAG_OBJECT": "b" * 64,
            "OBJECT_FORMAT": "sha256",
            "SIGNER": "code@vkut.me",
            "SOURCE_BASE": "https://git.vkut.me",
            "RUN_URL": "https://github.com/v-kut/cgit-release-builder/actions/runs/42",
            "ATTESTATION_URL": "https://github.com/v-kut/cgit-release-builder/attestations/99",
            "GITHUB_SHA": "deadbeef" * 5,
            "GITHUB_WORKFLOW_REF": "v-kut/cgit-release-builder/.github/workflows/rust.yml@refs/heads/main",
            "GITHUB_REPOSITORY": "v-kut/cgit-release-builder",
        }

    def test_release_json_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "out")
            out.mkdir()
            payload = b"binary-tarball"
            (out / "demo-1.2.3-aarch64-unknown-linux-gnu.tar.gz").write_bytes(b"arm")
            (out / "demo-1.2.3-x86_64-unknown-linux-gnu.tar.gz").write_bytes(payload)

            env = self._env() | {"NOTES": "- Fixed a bug\n"}
            with mock.patch.dict(os.environ, env, clear=True):
                data = json.loads(release.release_json(out))
                md = release.notes(data)

            self.assertEqual(data["signer"], "code@vkut.me")
            self.assertEqual(data["builder_commit"], "deadbeef" * 5)
            x86 = next(a for a in data["assets"] if "x86_64" in a["name"])
            self.assertEqual(x86["size"], len(payload))
            self.assertEqual(x86["sha256"], hashlib.sha256(payload).hexdigest())

            self.assertTrue(md.startswith("- Fixed a bug\n\n## Provenance"))
            self.assertIn(f"blob/{'deadbeef' * 5}/allowed_signers", md)
            self.assertIn("gh attestation verify demo-1.2.3-x86_64-unknown-linux-gnu.tar.gz", md)

    def test_notes_suppresses_redundant_tag_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "out")
            out.mkdir()
            (out / "demo-1.2.3.tgz").write_bytes(b"pkg")

            env = self._env() | {"NOTES": "demo 1.2.3\n"}
            with mock.patch.dict(os.environ, env, clear=True):
                data = json.loads(release.release_json(out))
                md = release.notes(data)

            self.assertTrue(md.startswith("## Provenance"))


if __name__ == "__main__":
    unittest.main()
