"""core/patcher.py -- primitive (L2): SEARCH/REPLACE patch applicator with hard uniqueness.

This module implements the deterministic SEARCH/REPLACE patching strategy
(blueprint §6.3). Every patch is validated for uniqueness BEFORE touching
disk; ambiguous or not-found searches are rejected typedly (NEVER fuzzy-matched).

All-or-nothing: if ANY block fails uniqueness or edge validation, NO file is
written. Writes happen only after ALL blocks pass every check.

Only LF line-endings accepted. Files containing \\r are rejected early,
preserving bytes outside replacement spans.

Paths are canonicalised once via ``resolve()``, symlinks are rejected,
and containment under ``workspace_root`` is verified — preventing alias
escapes and symlink-based sandbox bypass.

Replacements use precomputed spans on the ORIGINAL content (never re-search
after content mutation). Write+commit+verify wrapped in try/except with
in-memory byte-snapshot restore — the repo is never left written without
commit or revert.

Commit atómico vía core.gitrepo; self-check post-write con revert si falla.

Layering: L2 primitive. Imports core.gitrepo, core.trace and stdlib.
No reference to phases, oracle, llm or state.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PatchStatus(str, Enum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    VERIFY_FAILED = "verify_failed"


@dataclass
class Block:
    file: str
    search: str
    replace: str


@dataclass
class PatchResult:
    status: PatchStatus
    detail: str
    commit_sha: str = ""
    files_touched: list[str] = field(default_factory=list)


_BLOCK_RE = re.compile(
    r"(?:^|\n)[ \t]*FILE:[ \t]*([^\n]+?)[ \t]*\n"
    r"[ \t]*<<<<<<<[ \t]+SEARCH[ \t]*\n"
    r"(.*?)"
    r"\n[ \t]*=======[ \t]*\n"
    r"(.*?)"
    r"\n[ \t]*>>>>>>>[ \t]+REPLACE[ \t]*(?=\n|$)",
    re.DOTALL,
)

_FILE_MARKER_RE = re.compile(r"(?:^|\n)[ \t]*FILE:[ \t]*[^\n]+")
_SEARCH_MARKER_RE = re.compile(r"[ \t]*<<<<<<<[ \t]+SEARCH")
_REPLACE_MARKER_RE = re.compile(r"[ \t]*>>>>>>>[ \t]+REPLACE")


def parse_blocks(patch_text: str) -> list[Block]:
    """Parse SEARCH/REPLACE blocks. Returns ``[]`` if ANY marker is unconsumed
    (malformed/truncated block -- Critical fix #1: never silently ignore a
    partially-formed block)."""
    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    for m in _BLOCK_RE.finditer(normalized):
        blocks.append(Block(file=m.group(1).strip(), search=m.group(2), replace=m.group(3)))

    file_count = len(_FILE_MARKER_RE.findall(normalized))
    search_count = len(_SEARCH_MARKER_RE.findall(normalized))
    replace_count = len(_REPLACE_MARKER_RE.findall(normalized))

    if file_count != len(blocks) or search_count != len(blocks) or replace_count != len(blocks):
        return []

    return blocks


def _safe_canonical(file_path: str, workspace_root: str) -> str | None:
    """Canonicalize *file_path* and verify it is safe.

    Returns the absolute canonical path or ``None`` when:
    - the resolved path is a symlink (Critical fix #3)
    - the resolved path escapes ``workspace_root`` (Critical fix #2: alias
      ``./f.cu`` resolves to the same real file as ``f.cu``).
    """
    p = Path(workspace_root) / file_path
    if p.is_symlink():
        return None
    resolved = p.resolve()
    ws_resolved = Path(workspace_root).resolve()
    try:
        resolved.relative_to(ws_resolved)
    except ValueError:
        return None
    return str(resolved)


def _find_all_positions(haystack: str, needle: str) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    if not needle:
        return positions
    start = 0
    nlen = len(needle)
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append((idx, idx + nlen))
        start = idx + 1
    return positions


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def apply_patch(
    patch_text: str,
    repo,
    commit_message: str,
    trace=None,
) -> PatchResult:
    workspace_root = str(repo._repo.working_dir)

    blocks = parse_blocks(patch_text)
    if not blocks:
        return PatchResult(PatchStatus.INVALID, "sin bloques SEARCH/REPLACE válidos")

    for blk in blocks:
        if not blk.search.strip():
            return PatchResult(PatchStatus.INVALID, f"SEARCH vacío en archivo '{blk.file}'")

    for blk in blocks:
        if blk.replace == blk.search:
            return PatchResult(
                PatchStatus.INVALID, f"REPLACE igual a SEARCH (no-op) en archivo '{blk.file}'"
            )

    canonical: dict[str, str] = {}
    cpath_set: set[str] = set()
    for blk in blocks:
        cp = _safe_canonical(blk.file, workspace_root)
        if cp is None:
            return PatchResult(
                PatchStatus.INVALID, f"path inseguro, symlink o fuera del workspace: '{blk.file}'"
            )
        canonical[blk.file] = cp
        cpath_set.add(cp)

    for cp in cpath_set:
        if not os.path.isfile(cp):
            return PatchResult(
                PatchStatus.INVALID, f"archivo no existe: '{os.path.basename(cp)}'"
            )

    raw_snapshot: dict[str, bytes] = {}
    original_text: dict[str, str] = {}
    for cp in cpath_set:
        try:
            with open(cp, "rb") as f:
                raw_snapshot[cp] = f.read()
        except OSError:
            return PatchResult(PatchStatus.INVALID, f"error leyendo: '{os.path.basename(cp)}'")

        try:
            txt = raw_snapshot[cp].decode("utf-8")
        except UnicodeDecodeError:
            return PatchResult(PatchStatus.INVALID, f"archivo binario: '{os.path.basename(cp)}'")

        if "\r" in txt:
            return PatchResult(
                PatchStatus.INVALID,
                f"line endings no-LF en: '{os.path.relpath(cp, workspace_root)}'",
            )
        original_text[cp] = txt

    block_cpaths: list[str] = []
    block_spans: list[tuple[int, int]] = []
    for blk in blocks:
        cp = canonical[blk.file]
        block_cpaths.append(cp)
        positions = _find_all_positions(original_text[cp], blk.search)
        count = len(positions)
        if count == 0:
            return PatchResult(PatchStatus.NOT_FOUND, f"'{blk.file}': SEARCH no encontrado")
        if count > 1:
            return PatchResult(
                PatchStatus.AMBIGUOUS, f"'{blk.file}': SEARCH aparece {count} veces"
            )
        block_spans.append(positions[0])

    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if block_cpaths[i] == block_cpaths[j]:
                if _ranges_overlap(block_spans[i], block_spans[j]):
                    return PatchResult(
                        PatchStatus.INVALID,
                        f"bloques solapados en archivo '{blocks[i].file}'",
                    )

    if trace is not None:
        display_files = sorted({os.path.relpath(cp, workspace_root) for cp in cpath_set})
        trace.emit("patch_attempt", files=display_files, blocks=len(blocks), all_unique=True)

    modified_content: dict[str, str] = {}
    for cp in cpath_set:
        txt = original_text[cp]
        ops_info = []
        for idx, blk in enumerate(blocks):
            if block_cpaths[idx] == cp:
                ops_info.append((block_spans[idx][0], blk))
        ops_info.sort(key=lambda x: x[0], reverse=True)
        for start, blk in ops_info:
            end = start + len(blk.search)
            if txt[start:end] != blk.search:
                return PatchResult(
                    PatchStatus.INVALID, f"inconsistencia de span en '{blk.file}'"
                )
            txt = txt[:start] + blk.replace + txt[end:]
        modified_content[cp] = txt

    sha = ""
    try:
        for cp in cpath_set:
            with open(cp, "w", encoding="utf-8", newline="\n") as f:
                f.write(modified_content[cp])

        sha = repo.commit_all(commit_message)

        for blk in blocks:
            cp = canonical[blk.file]
            with open(cp, "r", encoding="utf-8") as f:
                content_after = f.read()
            if blk.replace not in content_after:
                if sha:
                    repo.revert_head()
                return PatchResult(
                    PatchStatus.VERIFY_FAILED,
                    f"'{blk.file}': REPLACE no verificado tras escritura",
                )

    except Exception as exc:
        for cp, raw in raw_snapshot.items():
            try:
                os.chmod(cp, 0o644)
                with open(cp, "wb") as f:
                    f.write(raw)
            except OSError:
                pass
        if sha:
            try:
                repo.revert_head()
            except Exception:
                pass
        return PatchResult(PatchStatus.INVALID, f"error interno: {exc}")

    return PatchResult(
        PatchStatus.APPLIED,
        f"{len(blocks)} bloques aplicados",
        commit_sha=sha,
        files_touched=sorted({os.path.relpath(cp, workspace_root) for cp in cpath_set}),
    )
