"""tests/test_gitrepo.py — pure L2 tests for ``core.gitrepo``.

All tests build local git repos in ``tmp_path`` (no network, no real
clones). Each test is hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from core.gitrepo import GitRepo, GitRepoError


def _init_repo_with_commit(
    path: Path,
    filename: str = "README.md",
    content: str = "hello",
    message: str = "initial commit",
) -> None:
    """Create a brand-new git repo at ``path`` with one committed file.

    Sets a local user identity so the commit is accepted even on hosts
    with no global git config. Uses local config only — never touches
    the host ``~/.gitconfig``.
    """
    repo = Repo.init(path)
    cfg = repo.config_writer()
    try:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@example.com")
    finally:
        cfg.release()
    (path / filename).write_text(content)
    repo.index.add([filename])
    repo.index.commit(message)


def test_checkout_branch_creates_and_switches(tmp_path: Path) -> None:
    repo_dir = tmp_path / "src"
    repo_dir.mkdir()
    _init_repo_with_commit(repo_dir)

    gr = GitRepo(str(repo_dir))

    # Initial state: some default branch exists and is current.
    initial = gr.current_branch()
    assert initial, "freshly committed repo should have a current branch"

    gr.checkout_branch("feature-x")
    assert gr.current_branch() == "feature-x"
    assert gr.head_sha(), "checkout on a committed repo must keep HEAD valid"

    # Calling again on the same name must be a no-op (idempotent).
    gr.checkout_branch("feature-x")
    assert gr.current_branch() == "feature-x"

    # And it must also let us switch back to an existing branch.
    gr.checkout_branch(initial)
    assert gr.current_branch() == initial


def test_commit_all_returns_sha_and_empty_when_clean(tmp_path: Path) -> None:
    repo_dir = tmp_path / "src"
    repo_dir.mkdir()
    _init_repo_with_commit(repo_dir, filename="file.txt", content="v1")
    gr = GitRepo(str(repo_dir))

    sha_initial = gr.head_sha()
    assert sha_initial, "after init commit we expect a real short sha"

    # Clean tree → empty string, NO exception.
    assert gr.commit_all("nothing to do") == ""
    assert gr.head_sha() == sha_initial

    # Modify a tracked file → real short sha, HEAD advances.
    (repo_dir / "file.txt").write_text("v2")
    sha_v2 = gr.commit_all("v2 edit")
    assert sha_v2 and len(sha_v2) >= 7
    assert sha_v2 != sha_initial
    assert gr.head_sha() == sha_v2

    # Tree is clean again → empty string.
    assert gr.commit_all("still nothing") == ""
    assert gr.head_sha() == sha_v2


def test_revert_head_restores_tree_exactly(tmp_path: Path) -> None:
    repo_dir = tmp_path / "src"
    repo_dir.mkdir()
    _init_repo_with_commit(repo_dir, filename="data.txt", content="v1")
    gr = GitRepo(str(repo_dir))

    sha_before = gr.head_sha()
    content_before = (repo_dir / "data.txt").read_text()

    # Bad edit: simulate a patch that broke the build.
    (repo_dir / "data.txt").write_text("v2 broken")
    sha_after_bad = gr.commit_all("introduce v2 broken")
    assert sha_after_bad != sha_before
    assert (repo_dir / "data.txt").read_text() == "v2 broken"

    gr.revert_head()

    # Tree EXACTLY as before: both the SHA and the file content.
    assert gr.head_sha() == sha_before
    assert (repo_dir / "data.txt").read_text() == content_before
    assert not gr.is_dirty()

    # And we can keep working after a revert: new edits commit fine.
    (repo_dir / "data.txt").write_text("v3 good")
    sha_v3 = gr.commit_all("v3 good")
    assert sha_v3 and sha_v3 != sha_before
    assert (repo_dir / "data.txt").read_text() == "v3 good"


def test_is_dirty_reflects_working_tree_state(tmp_path: Path) -> None:
    repo_dir = tmp_path / "src"
    repo_dir.mkdir()
    _init_repo_with_commit(repo_dir)
    gr = GitRepo(str(repo_dir))

    # Clean right after a commit.
    assert gr.is_dirty() is False

    # Modify a tracked file → dirty.
    (repo_dir / "README.md").write_text("modified")
    assert gr.is_dirty() is True

    # Commit → clean again.
    gr.commit_all("modification")
    assert gr.is_dirty() is False


def test_clone_classmethod_initialises_identity(tmp_path: Path) -> None:
    # Simulate a "remote" by making a local bare-ish repo and cloning it
    # via the file:// URL. This stays offline.
    src = tmp_path / "origin"
    src.mkdir()
    _init_repo_with_commit(src, filename="hello.txt", content="hi from origin")

    dest = tmp_path / "clone"
    gr = GitRepo.clone(f"file://{src}", str(dest))

    assert (dest / "hello.txt").read_text() == "hi from origin"
    assert gr.head_sha()
    assert not gr.is_dirty()
    assert gr.current_branch()

    # The clone must already have the pipeline identity configured,
    # so the very first commit_all here succeeds without further setup.
    (dest / "hello.txt").write_text("patched")
    sha = gr.commit_all("pipeline patch")
    assert sha and sha == gr.head_sha()
