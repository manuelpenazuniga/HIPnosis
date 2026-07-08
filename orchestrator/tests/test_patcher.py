"""tests/test_patcher.py -- L2 tests for ``core.patcher``.

Tests cover: APPLIED, NOT_FOUND, AMBIGUOUS, INVALID edge cases,
all-or-nothing atomicity, multi-file, trace emission, and 6 auditor-regression cases.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from git import Repo

from core.gitrepo import GitRepo
from core.trace import TraceWriter
from core.patcher import (
    Block,
    PatchResult,
    PatchStatus,
    apply_patch,
    parse_blocks,
)


def _make_repo(path: Path, files: dict[str, str]) -> GitRepo:
    repo = Repo.init(path)
    cfg = repo.config_writer()
    try:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@example.com")
    finally:
        cfg.release()
    for fname, content in files.items():
        (path / fname).write_text(content, encoding="utf-8")
    repo.index.add(list(files.keys()))
    repo.index.commit("initial commit")
    return GitRepo(str(path))


def _read(path: Path, fname: str) -> str:
    return (path / fname).read_text(encoding="utf-8")


def _patch(*blocks) -> str:
    parts: list[str] = []
    for b in blocks:
        parts.append(f"FILE: {b.file}")
        parts.append("<<<<<<< SEARCH")
        parts.append(b.search)
        parts.append("=======")
        parts.append(b.replace)
        parts.append(">>>>>>> REPLACE")
    return "\n".join(parts)


class TestParseBlocks:
    def test_single_block(self):
        text = (
            "FILE: src/main.cu\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].file == "src/main.cu"
        assert blocks[0].search == "old"
        assert blocks[0].replace == "new"

    def test_multiple_blocks(self):
        text = (
            "FILE: a.cu\n"
            "<<<<<<< SEARCH\n"
            "foo\n"
            "=======\n"
            "bar\n"
            ">>>>>>> REPLACE\n"
            "FILE: b.cu\n"
            "<<<<<<< SEARCH\n"
            "xyz\n"
            "=======\n"
            "abc\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].file == "a.cu"
        assert blocks[1].file == "b.cu"

    def test_multiline_search_and_replace(self):
        text = (
            "FILE: kernel.cu\n"
            "<<<<<<< SEARCH\n"
            "line1\n"
            "line2\n"
            "=======\n"
            "new1\n"
            "new2\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].search == "line1\nline2"
        assert blocks[0].replace == "new1\nnew2"

    def test_tolerates_spaces_around_markers(self):
        text = (
            "  FILE:   file.cu   \n"
            "  <<<<<<< SEARCH  \n"
            "old\n"
            "  =======  \n"
            "new\n"
            "  >>>>>>> REPLACE  \n"
        )
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].file == "file.cu"
        assert blocks[0].search == "old"
        assert blocks[0].replace == "new"

    def test_empty_patch_returns_empty_list(self):
        assert parse_blocks("") == []
        assert parse_blocks("just some text") == []

    def test_search_with_trailing_spaces(self):
        text = (
            "FILE: f.cu\n"
            "<<<<<<< SEARCH\n"
            "hello  \n"
            "=======\n"
            "bye\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_blocks(text)
        assert blocks[0].search == "hello  "

    def test_crlf_normalized(self):
        text = (
            "FILE: f.cu\r\n"
            "<<<<<<< SEARCH\r\n"
            "old\r\n"
            "=======\r\n"
            "new\r\n"
            ">>>>>>> REPLACE\r\n"
        )
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].search == "old"
        assert blocks[0].replace == "new"

    # -- Regression #1: malformed block (truncated marker) rejects entire patch --
    def test_malformed_block_rejects_entire_patch(self):
        text = (
            "FILE: a.cu\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "FILE: b.cu\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>> REPLACE\n"
        )
        blocks = parse_blocks(text)
        assert blocks == []


class TestApplyPatchApplied:
    def test_single_block_applied(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"main.cu": "hello\nworld\n"})
        sha_before = repo.head_sha()

        patch = _patch(Block("main.cu", "hello", "hi"))
        result = apply_patch(patch, repo, "fix: replace hello")

        assert result.status == PatchStatus.APPLIED
        assert result.commit_sha != ""
        assert result.commit_sha != sha_before
        assert result.files_touched == ["main.cu"]
        assert _read(repo_dir, "main.cu") == "hi\nworld\n"
        assert repo.head_sha() == result.commit_sha

    def test_verify_replace_present_after_write(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        _make_repo(repo_dir, {"f.cu": "int x = 42;\n"})

        patch = _patch(Block("f.cu", "int x = 42;", "int x = 43;"))
        result = apply_patch(patch, GitRepo(str(repo_dir)), "fix")
        assert result.status == PatchStatus.APPLIED
        assert "int x = 43;" in _read(repo_dir, "f.cu")

    def test_multi_block_same_file(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        _make_repo(repo_dir, {"f.cu": "AAA\nBBB\nCCC\n"})

        patch = _patch(
            Block("f.cu", "AAA", "111"),
            Block("f.cu", "CCC", "333"),
        )
        result = apply_patch(patch, GitRepo(str(repo_dir)), "double fix")
        assert result.status == PatchStatus.APPLIED
        assert len(result.files_touched) == 1
        assert _read(repo_dir, "f.cu") == "111\nBBB\n333\n"

    def test_multi_file_applied(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        _make_repo(
            repo_dir,
            {"a.cu": "alpha\n", "b.cu": "beta\n"},
        )
        gr = GitRepo(str(repo_dir))

        patch = _patch(
            Block("a.cu", "alpha", "ALPHA"),
            Block("b.cu", "beta", "BETA"),
        )
        result = apply_patch(patch, gr, "multi-file")
        assert result.status == PatchStatus.APPLIED
        assert sorted(result.files_touched) == ["a.cu", "b.cu"]
        assert _read(repo_dir, "a.cu") == "ALPHA\n"
        assert _read(repo_dir, "b.cu") == "BETA\n"
        assert result.commit_sha == gr.head_sha()


class TestApplyPatchNotFound:
    def test_search_not_found(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "hello\n"})
        sha_before = repo.head_sha()

        patch = _patch(Block("f.cu", "nonexistent", "replace"))
        result = apply_patch(patch, repo, "fix")

        assert result.status == PatchStatus.NOT_FOUND
        assert result.commit_sha == ""
        assert result.files_touched == []
        assert _read(repo_dir, "f.cu") == "hello\n"
        assert repo.head_sha() == sha_before

    def test_not_found_no_commit(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"x.cu": "data\n"})
        sha_before = repo.head_sha()

        apply_patch(_patch(Block("x.cu", "missing", "x")), repo, "msg")
        assert repo.head_sha() == sha_before
        assert not repo.is_dirty()


class TestApplyPatchAmbiguous:
    def test_ambiguous_search(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "dup\ndup\n"})
        sha_before = repo.head_sha()

        patch = _patch(Block("f.cu", "dup", "fixed"))
        result = apply_patch(patch, repo, "fix")

        assert result.status == PatchStatus.AMBIGUOUS
        assert result.commit_sha == ""
        assert "aparece 2 veces" in result.detail
        assert _read(repo_dir, "f.cu") == "dup\ndup\n"
        assert repo.head_sha() == sha_before

    def test_ambiguous_does_not_write(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "x\nx\n"})
        sha_before = repo.head_sha()

        apply_patch(_patch(Block("f.cu", "x", "y")), repo, "msg")
        assert _read(repo_dir, "f.cu") == "x\nx\n"
        assert repo.head_sha() == sha_before


class TestApplyPatchInvalid:
    def test_empty_search(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "content\n"})

        patch = _patch(Block("f.cu", "", "replace"))
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "SEARCH vacío" in result.detail

    def test_replace_equals_search_noop(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "x\n"})
        sha_before = repo.head_sha()

        patch = _patch(Block("f.cu", "x", "x"))
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "no-op" in result.detail
        assert repo.head_sha() == sha_before

    def test_path_with_dot_dot(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "x\n"})

        patch = _patch(Block("../escape.cu", "x", "y"))
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "inseguro" in result.detail

    def test_file_not_found(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "x\n"})

        patch = _patch(Block("noexist.cu", "x", "y"))
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "no existe" in result.detail

    def test_overlapping_blocks_invalid(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "hello world foo\n"})
        sha_before = repo.head_sha()

        patch = _patch(
            Block("f.cu", "hello world", "AAA"),
            Block("f.cu", "world foo", "BBB"),
        )
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "solapados" in result.detail
        assert _read(repo_dir, "f.cu") == "hello world foo\n"
        assert repo.head_sha() == sha_before

    def test_empty_blocks_returns_invalid(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "x\n"})

        result = apply_patch("no markers here", repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "sin bloques" in result.detail


class TestAllOrNothing:
    def test_multi_block_one_not_found_nothing_written(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(
            repo_dir,
            {"valid.cu": "alpha\n", "other.cu": "beta\n"},
        )
        sha_before = repo.head_sha()

        patch = _patch(
            Block("valid.cu", "alpha", "FIXED"),
            Block("other.cu", "nonexistent", "x"),
        )
        result = apply_patch(patch, repo, "fix")

        assert result.status == PatchStatus.NOT_FOUND
        assert _read(repo_dir, "valid.cu") == "alpha\n"
        assert _read(repo_dir, "other.cu") == "beta\n"
        assert repo.head_sha() == sha_before
        assert not repo.is_dirty()

    def test_multi_block_one_ambiguous_nothing_written(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(
            repo_dir,
            {"valid.cu": "alpha\n", "dup.cu": "x\nx\n"},
        )
        sha_before = repo.head_sha()

        patch = _patch(
            Block("valid.cu", "alpha", "FIXED"),
            Block("dup.cu", "x", "y"),
        )
        result = apply_patch(patch, repo, "fix")

        assert result.status == PatchStatus.AMBIGUOUS
        assert _read(repo_dir, "valid.cu") == "alpha\n"
        assert _read(repo_dir, "dup.cu") == "x\nx\n"
        assert repo.head_sha() == sha_before

    def test_multi_block_one_invalid_nothing_written(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"valid.cu": "alpha\n"})
        sha_before = repo.head_sha()

        patch = _patch(
            Block("valid.cu", "alpha", "FIXED"),
            Block("noexist.cu", "x", "y"),
        )
        result = apply_patch(patch, repo, "fix")

        assert result.status == PatchStatus.INVALID
        assert _read(repo_dir, "valid.cu") == "alpha\n"
        assert repo.head_sha() == sha_before


class TestTrace:
    def test_patch_attempt_emitted_before_write(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "hello\n"})

        trace_path = str(tmp_path / "trace.jsonl")
        trace = TraceWriter(trace_path, "run_test")

        patch = _patch(Block("f.cu", "hello", "hi"))
        result = apply_patch(patch, repo, "fix", trace=trace)

        assert result.status == PatchStatus.APPLIED

        lines = Path(trace_path).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["ev"] == "patch_attempt"
        assert ev["files"] == ["f.cu"]
        assert ev["blocks"] == 1
        assert ev["all_unique"] is True

    def test_patch_attempt_not_emitted_on_not_found(self, tmp_path: Path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "hello\n"})

        trace_path = str(tmp_path / "trace.jsonl")
        trace = TraceWriter(trace_path, "run_test")

        patch = _patch(Block("f.cu", "missing", "x"))
        apply_patch(patch, repo, "fix", trace=trace)

        assert not Path(trace_path).exists()


# ====== AUDITOR REGRESSION TESTS (6 critical bugs) ======


class TestRegression:
    """Auditor regression: concrete cases for the 6 critical bugs."""

    def test_regression_01_malformed_block_ignored(self, tmp_path: Path):
        """Critical #1: a block with truncated ``>>>>>> REPLACE`` must
        reject the entire patch — never silently ignore it and apply the
        remaining blocks."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"a.cu": "old\n", "b.cu": "old\n"})
        sha_before = repo.head_sha()

        patch = (
            "FILE: a.cu\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "FILE: b.cu\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>> REPLACE\n"
        )
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "sin bloques" in result.detail
        assert _read(repo_dir, "a.cu") == "old\n"
        assert _read(repo_dir, "b.cu") == "old\n"
        assert repo.head_sha() == sha_before

    def test_regression_02_path_alias_same_file(self, tmp_path: Path):
        """Critical #2: ``f.cu`` and ``./f.cu`` must canonicalise to
        the same file. Both blocks apply and the file is patched once."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "old1\nold2\n"})
        sha_before = repo.head_sha()

        patch = _patch(
            Block("f.cu", "old1", "NEW1"),
            Block("./f.cu", "old2", "NEW2"),
        )
        result = apply_patch(patch, repo, "alias fix")
        assert result.status == PatchStatus.APPLIED
        assert _read(repo_dir, "f.cu") == "NEW1\nNEW2\n"
        assert result.commit_sha != sha_before

    def test_regression_03_symlink_escapes_workspace(self, tmp_path: Path):
        """Critical #3: a symlink pointing outside the workspace must be
        rejected — never follow it and write outside."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        outside = tmp_path / "outside.cu"
        outside.write_text("secret\n", encoding="utf-8")
        link = repo_dir / "link.cu"
        os.symlink(str(outside), str(link))

        repo = _make_repo(repo_dir, {"main.cu": "hello\n"})
        sha_before = repo.head_sha()

        patch = _patch(Block("link.cu", "secret", "leaked"))
        result = apply_patch(patch, repo, "fix")
        assert result.status == PatchStatus.INVALID
        assert "inseguro" in result.detail or "symlink" in result.detail
        assert outside.read_text(encoding="utf-8") == "secret\n"
        assert repo.head_sha() == sha_before

    def test_regression_04_non_lf_line_endings(self, tmp_path: Path):
        """Critical #4: a file with ``\\r`` endings must be rejected
        before writing, preserving all bytes outside the replacement span."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "f.cu").write_bytes(b"a\r\nb\nc\rd\nint x = 0;\n")

        repo = Repo.init(repo_dir)
        cfg = repo.config_writer()
        try:
            cfg.set_value("user", "name", "Test")
            cfg.set_value("user", "email", "test@example.com")
        finally:
            cfg.release()
        repo.index.add(["f.cu"])
        repo.index.commit("init")
        gr = GitRepo(str(repo_dir))
        sha_before = gr.head_sha()

        patch = _patch(Block("f.cu", "int x = 0;", "int x = 1;"))
        result = apply_patch(patch, gr, "fix")
        assert result.status == PatchStatus.INVALID
        assert "no-LF" in result.detail
        assert (repo_dir / "f.cu").read_bytes() == b"a\r\nb\nc\rd\nint x = 0;\n"
        assert gr.head_sha() == sha_before

    def test_regression_05_precomputed_spans_no_research(self, tmp_path: Path):
        """Critical #5: when REPLACE of Block 2 introduces SEARCH of Block 1,
        precomputed spans prevent ambiguous re-search on mutated content."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(repo_dir, {"f.cu": "A\nB\n"})
        sha_before = repo.head_sha()

        patch = _patch(
            Block("f.cu", "A", "X"),
            Block("f.cu", "B", "B\nA"),
        )
        result = apply_patch(patch, repo, "tricky")
        assert result.status == PatchStatus.APPLIED
        assert _read(repo_dir, "f.cu") == "X\nB\nA\n"
        assert result.commit_sha != sha_before

    def test_regression_06_exception_restore_no_commit(self, tmp_path: Path):
        """Critical #6: an exception during commit (corrupted .git) restores
        modified files from in-memory snapshots — the repo is never left
        written without a commit or revert."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        gr = _make_repo(repo_dir, {"a.cu": "alpha\n", "b.cu": "beta\n"})
        sha_before = gr.head_sha()
        original_bytes = {
            "a.cu": (repo_dir / "a.cu").read_bytes(),
            "b.cu": (repo_dir / "b.cu").read_bytes(),
        }

        objects_dir = repo_dir / ".git" / "objects"
        objects_dir.chmod(0o500)

        patch = _patch(
            Block("a.cu", "alpha", "NEW"),
            Block("b.cu", "beta", "NEW2"),
        )
        result = apply_patch(patch, gr, "fix")

        objects_dir.chmod(0o700)

        assert result.status == PatchStatus.INVALID
        assert "error interno" in result.detail
        for fname, orig in original_bytes.items():
            assert (repo_dir / fname).read_bytes() == orig, f"{fname} not restored"
        assert gr.head_sha() == sha_before
