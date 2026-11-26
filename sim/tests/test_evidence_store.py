"""Unit tests for sim/harness/evidence_store.py (issue #198) -- hermetic: no
broker, no ngspice, no real `klt`. `klt artifact put` is faked."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import cli, mc_cli, evidence_store as store  # noqa: E402


def _stored_entry(data: bytes, name: str) -> dict:
    """One valid manifest entry for ``data``, stored under ``name``."""
    sha = hashlib.sha256(data).hexdigest()
    return {
        "sha256": sha, "size": len(data), "kind": "evidence",
        "producer": {"tool": "klt", "version": "0", "loom.repo": "o/r", "commit": None},
        "uri": f"artifact:evidence/o__r/{sha[:2]}/{sha}", "name": name,
    }


def _fake_put(files, repo_root):
    """Stand-in for put_files: a valid manifest with artifact: uris."""
    entries = [_stored_entry(Path(path).read_bytes(), name) for path, name in files]
    return {"schema_version": 1, "entries": sorted(entries, key=lambda e: e["name"])}, []


class TestPreflightFailsClosed(unittest.TestCase):
    def test_broker_unset(self):
        with self.assertRaisesRegex(store.StoreError, "KLT_ARTIFACT_BROKER"):
            store.preflight(Path("."), env={})

    def test_klt_missing(self):
        with self.assertRaisesRegex(store.StoreError, "not on PATH"):
            store.preflight(Path("."), env={store.ENV_BROKER: "http://b.invalid"},
                            which=lambda _: None)

    def test_klt_without_artifact_put(self):
        run = lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="")  # noqa: E731
        with self.assertRaisesRegex(store.StoreError, "no `artifact put` verb"):
            store.preflight(Path("."), env={store.ENV_BROKER: "http://b.invalid"},
                            which=lambda _: "/bin/klt", run=run)

    def test_broker_unreachable(self):
        def probe(*_a):
            raise store.StoreError("artifact broker unreachable (OSError)")
        probe_err = json.dumps(
            {"error": {"code": "invalid_manifest", "problems": ["uri: artifact: only"]}})

        def run(cmd, **_k):
            if "put" in cmd:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr=probe_err)
        env = {store.ENV_BROKER: "http://b.invalid", store.ENV_REPO: "o/r"}
        with self.assertRaisesRegex(store.StoreError, "unreachable"):
            store.preflight(Path("."), env=env, which=lambda _: "/bin/klt", run=run, probe=probe)

    def test_old_klt_is_refused(self):
        # An old klt accepts the legacy-scheme probe manifest (no problems).
        run = lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="")  # noqa: E731
        with self.assertRaisesRegex(store.StoreError, "older than klayout-tools"):
            store.check_klt_uri_scheme("/bin/klt", run=run)


class TestStoreRun(unittest.TestCase):
    def _repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        exp = root / "sim" / "bench"
        exp.mkdir(parents=True)
        return root, exp

    def test_commits_only_manifest_and_record(self):
        root, exp = self._repo()
        blobs = {"corners/rid1/tt.log": "log\n", "netlist-snapshots/rid1.spice": "* n\n"}
        mpath = store.store_run(repo_root=root, experiment_dir=exp, record_id="rid1",
                                blobs=blobs, record_text="# Record rid1\n", put=_fake_put)
        self.assertEqual(mpath, root / "manifests/artifacts/bench-rid1.manifest.json")
        manifest = json.loads(mpath.read_text())
        self.assertEqual([e["name"] for e in manifest["entries"]],
                         ["sim/bench/corners/rid1/tt.log", "sim/bench/netlist-snapshots/rid1.spice"])
        self.assertTrue(all(e["uri"].startswith("artifact:") for e in manifest["entries"]))
        self.assertIn("## Stored evidence", (exp / "records/rid1.md").read_text())
        # raw outputs are staged in the ignored scratch tree, never under the bench
        self.assertFalse((exp / "corners").exists())
        self.assertFalse((exp / "netlist-snapshots").exists())

    def test_put_failure_writes_nothing_tracked(self):
        root, exp = self._repo()

        def boom(files, repo_root):
            raise store.StoreError("broker refused")
        with self.assertRaises(store.StoreError):
            store.store_run(repo_root=root, experiment_dir=exp, record_id="rid2",
                            blobs={"corners/rid2/a.log": "x\n"}, record_text="r\n", put=boom)
        self.assertFalse((root / "manifests").exists())
        self.assertFalse((exp / "records").exists())
        self.assertTrue((root / "sim/.work/bench/rid2/corners/rid2/a.log").exists())

    def test_refuses_to_overwrite(self):
        root, exp = self._repo()
        kw = dict(repo_root=root, experiment_dir=exp, record_id="rid3",
                  blobs={"corners/rid3/a.log": "x\n"}, record_text="r\n", put=_fake_put)
        store.store_run(**kw)
        with self.assertRaisesRegex(store.StoreError, "already exists"):
            store.store_run(**kw)

    def test_free_record_id_advances_past_taken(self):
        root, exp = self._repo()
        rid = "20261023-000000-abc1234"
        store.store_run(repo_root=root, experiment_dir=exp, record_id=rid,
                        blobs={"corners/x/a.log": "x\n"}, record_text="r\n", put=_fake_put)
        self.assertEqual(store.free_record_id(root, exp, rid), "20261023-000001-abc1234")

    def test_empty_staging_is_refused(self):
        root, exp = self._repo()
        with self.assertRaisesRegex(store.StoreError, "nothing staged"):
            store.store_run(repo_root=root, experiment_dir=exp, record_id="rid4",
                            blobs={}, record_text="r\n", put=_fake_put)


class TestPutFilesValidatesWholeManifest(unittest.TestCase):
    """The manifest ``klt`` answers with is validated whole, against the same
    schema the CI gate applies, before entries are indexed by name (issue
    #389): two identical entries must be refused, not collapsed into one for
    the staged-file cross-check and then both returned."""

    NAME = "sim/bench/corners/rid/tt.log"

    def _put(self, klt_entries):
        """``put_files`` on one log, with a ``klt`` stand-in that answers
        ``klt_entries(<the valid entry for that log>)``."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        log = root / "tt.log"
        log.write_text("log\n")

        def run(cmd, **_k):
            entries = klt_entries(_stored_entry(log.read_bytes(), self.NAME))
            mpath = cmd[cmd.index("--manifest") + 1]
            Path(mpath).write_text(json.dumps({"schema_version": 1, "entries": entries}))
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return store.put_files([(log, self.NAME)], root, run=run)

    def test_single_entry_control_is_returned(self):
        manifest, empty = self._put(lambda e: [e])
        self.assertEqual([e["name"] for e in manifest["entries"]], [self.NAME])
        self.assertEqual(empty, [])

    def test_duplicate_entry_is_refused(self):
        with self.assertRaisesRegex(store.StoreError, "duplicate name"):
            self._put(lambda e: [e, dict(e)])


_RECORD_CLI_CASES = [
    # (label, module, argv, patched runner target)
    ("run_corners", cli, ["harness-corner-smoke", "--record"], "harness.runner.run"),
    ("monte_carlo", mc_cli, ["mc-smoke", "--record", "--seed", "1", "--n", "2"],
     "harness.mc_runner.run"),
]


class TestCliFailsClosed(unittest.TestCase):
    def test_record_without_broker_exits_nonzero_before_simulating(self):
        for label, module, argv, runner_target in _RECORD_CLI_CASES:
            with self.subTest(cli=label):
                err = io.StringIO()
                env = {k: v for k, v in os.environ.items() if k != store.ENV_BROKER}
                with unittest.mock.patch.dict("os.environ", env, clear=True), \
                        unittest.mock.patch(runner_target) as run, \
                        contextlib.redirect_stderr(err):
                    rc = module.main(argv)
                self.assertEqual(rc, 10)
                run.assert_not_called()
                self.assertIn("KLT_ARTIFACT_BROKER", err.getvalue())


if __name__ == "__main__":
    unittest.main()
