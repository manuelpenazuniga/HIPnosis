"""core/gitrepo.py — primitive (L2): git wrapper for the TARGET repo workspace.

This module is the ONLY door through which the pipeline writes git history
on the target repo. Filesystem mutations performed by the patcher (L2
``core.patcher``) land on disk; ``core.gitrepo`` is what records the
atomic commit that captures the change as a single, reversible unit
(blueprint INV-3). If a code path needs to write to the target repo and
make that change auditable, it MUST go through ``commit_all`` here.

Layering: L2 primitive. Imports only ``git`` (gitpython). No reference to
``phases``, ``oracle``, ``llm`` or ``state``. ``schemas`` / ``config`` may
be imported later for richer error typing, but the current contract is
deliberately self-contained so this module is trivially testable.
"""

from __future__ import annotations

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError


_COMMITTER_NAME = "HIPnosis Pipeline"
_COMMITTER_EMAIL = "pipeline@hipnosis.local"


class GitRepoError(RuntimeError):
    """Raised on git operations the pipeline must not silently ignore."""


class GitRepo:
    """Thin, opinionated wrapper around a git working tree (the target repo).

    The instance binds 1:1 to a path on disk. All operations act on that
    path. The class is *not* thread-safe across the same instance — the
    pipeline serialises access per workspace per run.
    """

    def __init__(self, path: str) -> None:
        try:
            self._repo = Repo(path)
        except NoSuchPathError as e:
            raise GitRepoError(f"workspace path does not exist: {path}") from e
        except InvalidGitRepositoryError as e:
            raise GitRepoError(f"not a git repository: {path}") from e

        self._ensure_local_identity()

    def _ensure_local_identity(self) -> None:
        """Make sure commits succeed regardless of the host's global git config.

        The pipeline is the legitimate author of the workspace it is
        porting, so we set ``user.name`` / ``user.email`` at the LOCAL
        scope (``.git/config`` of the workspace). We never touch the
        user's global ``~/.gitconfig``.
        """
        cfg = self._repo.config_writer()
        try:
            cfg.set_value("user", "name", _COMMITTER_NAME)
            cfg.set_value("user", "email", _COMMITTER_EMAIL)
        finally:
            cfg.release()

    @classmethod
    def clone(cls, url: str, dest: str) -> "GitRepo":
        """``git clone url dest`` (shallow, ``--depth 1``), return a GitRepo.

        Shallow is enough: the pipeline does not need the target repo's
        full history to port code. A full clone would waste minutes and
        gigabytes on real-world CUDA repos.
        """
        Repo.clone_from(url, dest, depth=1)
        return cls(dest)

    def checkout_branch(self, name: str) -> None:
        """Create ``name`` and switch to it; or switch to it if it exists.

        Equivalent to ``git checkout -b name`` when absent, plain
        ``git checkout name`` when present. Idempotent.
        """
        if name in {h.name for h in self._repo.heads}:
            self._repo.heads[name].checkout()
        else:
            self._repo.create_head(name).checkout()

    def commit_all(self, message: str) -> str:
        """``git add -A && git commit -m message``.

        Returns the short SHA of the new commit. If the working tree is
        clean (nothing to record), returns ``""`` and does NOT raise —
        atomicity demands the pipeline can call this unconditionally after
        a patch attempt without having to pre-check.

        The "nothing to commit" check considers untracked files too, so a
        freshly-added source file is correctly captured by ``git add -A``.
        """
        if not self._repo.is_dirty(untracked_files=True):
            return ""
        self._repo.git.add("-A")
        commit = self._repo.index.commit(message)
        return commit.hexsha[:7]

    def revert_head(self) -> None:
        """Hard-reset the LAST commit, leaving the tree as it was before.

        Implementation: ``git reset --hard HEAD~1``.

        Why ``--hard`` is acceptable here: the workspace is ephemeral,
        one per run. The pipeline has just made a single atomic edit
        (a patch attempt). If that edit broke the build and we want to
        roll it back, the simplest and most deterministic thing is to
        make the tree look exactly as it did before the commit. We do
        NOT need to preserve the discarded fix in history: it is already
        captured in the run's trace JSONL and in the run report. The
        atomicity guarantee is per-run, not per-fix.
        """
        try:
            self._repo.git.reset("--hard", "HEAD~1")
        except GitCommandError as e:
            raise GitRepoError(f"revert_head failed: {e}") from e

    def head_sha(self) -> str:
        """Short SHA of HEAD, or ``""`` if HEAD is unborn (no commits yet)."""
        try:
            return self._repo.head.commit.hexsha[:7]
        except ValueError:
            return ""

    def current_branch(self) -> str:
        """Current branch name, or ``""`` on detached or unborn HEAD."""
        if self._repo.head.is_detached:
            return ""
        try:
            self._repo.head.commit
        except ValueError:
            return ""
        return self._repo.head.reference.name

    def is_dirty(self) -> bool:
        """True if there are staged or unstaged changes to TRACKED files.

        Untracked files are NOT considered dirty here — that matches the
        git vernacular the pipeline uses elsewhere (a freshly extracted
        source tree has untracked files that are not yet "the pipeline's
        problem").
        """
        return self._repo.is_dirty()
