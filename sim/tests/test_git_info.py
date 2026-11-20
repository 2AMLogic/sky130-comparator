"""Unit tests for sim/harness/evidence.py's git_info() provenance contract
(issue #358): the repo-script batch route (RS_SOURCE_COMMIT /
RS_SYNTHETIC_HEAD, read by sim/comparator-decision/check-env-batch.sh and
exported by 2AMLogic/2am's infra/aws/repo-script-job-run.sh) must stamp the
REAL source commit, never the job tree's synthetic HEAD, and the absence of
any honest identity must fail closed instead of inventing a placeholder.

Hermetic: the only external tool used is git itself, against temporary
trees (or this repo's own checkout for the unchanged-ordinary-checkout
case). No ngspice, no PDK."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence  # noqa: E402


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@localhost",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_commit(root: Path) -> str:
    """A standalone git repo with one commit; returns its full sha."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "file.txt").write_text("tree\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "synthetic stand-in")
    return _git(root, "rev-parse", "HEAD")


class TestGitInfoBatchRoute(unittest.TestCase):
    """Issue #358 acceptance: archive tree + RS_SOURCE_COMMIT."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        # A `git archive` tree has no .git at all -- exactly what a
        # repo-script job's source root is before the harness stages its
        # synthetic work tree.
        self.archive_tree = Path(self._td.name) / "archive"
        self.archive_tree.mkdir()
        self.source_commit = "0123456789abcdef0123456789abcdef01234567"

    def test_archive_tree_with_source_commit(self):
        info = evidence.git_info(
            repo_root=self.archive_tree,
            env={evidence.ENV_SOURCE_COMMIT: self.source_commit},
        )
        self.assertEqual(info.commit, self.source_commit)
        self.assertEqual(info.branch, evidence.BATCH_ROUTE_BRANCH)
        self.assertFalse(info.dirty)

    def test_source_commit_wins_over_synthetic_head(self):
        # A job tree the harness HAS staged a git work tree on (a usable
        # `git rev-parse HEAD` that returns the SYNTHETIC local commit).
        # The variable must still win.
        synthetic_head = _make_commit(Path(self._td.name) / "jobtree")
        self.assertNotEqual(synthetic_head, self.source_commit)
        info = evidence.git_info(
            repo_root=Path(self._td.name) / "jobtree",
            env={evidence.ENV_SOURCE_COMMIT: self.source_commit,
                 evidence.ENV_SYNTHETIC_HEAD: "1"},
        )
        self.assertEqual(info.commit, self.source_commit)
        self.assertEqual(info.branch, evidence.BATCH_ROUTE_BRANCH)
        self.assertFalse(info.dirty)

    def test_record_id_suffix_follows_same_source(self):
        # new_record_id()'s short-commit suffix is the first 7 chars of
        # RS_SOURCE_COMMIT on the batch route -- never the synthetic HEAD
        # and never "nogit".
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {evidence.ENV_SOURCE_COMMIT: self.source_commit}):
            rid = evidence.new_record_id()
        self.assertTrue(rid.endswith("-" + self.source_commit[:7]), rid)


class TestGitInfoFailsClosed(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.bare_tree = Path(self._td.name) / "nogit"
        self.bare_tree.mkdir()

    def test_no_tree_no_variable(self):
        with self.assertRaisesRegex(evidence.GitProvenanceError, "RS_SOURCE_COMMIT"):
            evidence.git_info(repo_root=self.bare_tree, env={})

    def test_synthetic_head_without_source_commit(self):
        # RS_SYNTHETIC_HEAD=1 with an empty RS_SOURCE_COMMIT: the only git
        # identity in the tree is the synthetic one, which must NOT be
        # stamped as provenance.
        synthetic_tree = Path(self._td.name) / "synthetic"
        _make_commit(synthetic_tree)
        with self.assertRaisesRegex(evidence.GitProvenanceError, "synthetic"):
            evidence.git_info(repo_root=synthetic_tree,
                              env={evidence.ENV_SYNTHETIC_HEAD: "1"})

    def test_short_sha_is_nogit_when_only_synthetic_head(self):
        self.assertEqual(evidence._short_sha(env={evidence.ENV_SYNTHETIC_HEAD: "1"}),
                         "nogit")


class TestGitInfoOrdinaryCheckout(unittest.TestCase):
    def test_checkout_behaviour_unchanged(self):
        # The repo running these tests IS an ordinary checkout; env={} pins
        # the case even if the host ambient environment carries RS_* vars.
        info = evidence.git_info(env={})
        expected = subprocess.run(
            ["git", "-C", str(evidence.REPO_ROOT), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(info.commit, expected)
        self.assertNotEqual(info.branch, evidence.BATCH_ROUTE_BRANCH)
        self.assertIsInstance(info.dirty, bool)


if __name__ == "__main__":
    unittest.main()
