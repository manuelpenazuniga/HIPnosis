"""core/patcher.py -- primitive (L2): SEARCH/REPLACE patch applicator with hard uniqueness.

This module implements the deterministic SEARCH/REPLACE patching strategy
(blueprint §6.3). Every patch is validated for uniqueness BEFORE touching
disk; ambiguous or not-found searches are rejected typedly (NEVER fuzzy-matched).

All-or-nothing: if ANY block fails uniqueness or edge validation, NO file is
written. Writes happen only after ALL blocks pass every check.

Normaliza line endings (CRLF→LF) al leer; escribe LF consistente.
Commit atómico vía core.gitrepo; self-check post-write con revert si falla.

Layering: L2 primitive. Imports core.gitrepo, core.trace and stdlib.
No reference to phases, oracle, llm or state.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum


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


def parse_blocks(patch_text: str) -> list[Block]:
    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    for m in _BLOCK_RE.finditer(normalized):
        file_path = m.group(1).strip()
        search = m.group(2)
        replace = m.group(3)
        blocks.append(Block(file=file_path, search=search, replace=replace))
    return blocks


def _normalize(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _is_path_safe(file_path: str) -> bool:
    if not file_path:
        return False
    if os.path.isabs(file_path):
        return False
    parts = file_path.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        return False
    return True


def _is_binary_or_missing(file_path: str, ws_root: str) -> bool:
    full = os.path.join(ws_root, file_path)
    if not os.path.isfile(full):
        return True
    try:
        with open(full, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


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
            return PatchResult(
                PatchStatus.INVALID,
                f"SEARCH vacío en archivo '{blk.file}'",
            )

    for blk in blocks:
        if blk.replace == blk.search:
            return PatchResult(
                PatchStatus.INVALID,
                f"REPLACE igual a SEARCH (no-op) en archivo '{blk.file}'",
            )

    for blk in blocks:
        if not _is_path_safe(blk.file):
            return PatchResult(
                PatchStatus.INVALID,
                f"path inseguro o fuera del workspace: '{blk.file}'",
            )

    for blk in blocks:
        if _is_binary_or_missing(blk.file, workspace_root):
            return PatchResult(
                PatchStatus.INVALID,
                f"archivo binario o no existe: '{blk.file}'",
            )

    files_touched_set: set[str] = set()
    file_contents: dict[str, str] = {}

    for blk in blocks:
        files_touched_set.add(blk.file)

    for fname in files_touched_set:
        full = os.path.join(workspace_root, fname)
        try:
            with open(full, "r", encoding="utf-8") as f:
                raw = f.read()
        except UnicodeDecodeError:
            return PatchResult(
                PatchStatus.INVALID,
                f"archivo binario (no decodificable como UTF-8): '{fname}'",
            )
        file_contents[fname] = _normalize(raw)

    block_positions = []
    for blk in blocks:
        positions = _find_all_positions(file_contents[blk.file], blk.search)
        count = len(positions)
        if count == 0:
            return PatchResult(
                PatchStatus.NOT_FOUND,
                f"'{blk.file}': SEARCH no encontrado",
            )
        if count > 1:
            return PatchResult(
                PatchStatus.AMBIGUOUS,
                f"'{blk.file}': SEARCH aparece {count} veces",
            )
        block_positions.append(positions[0])

    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if blocks[i].file == blocks[j].file:
                if _ranges_overlap(block_positions[i], block_positions[j]):
                    return PatchResult(
                        PatchStatus.INVALID,
                        f"bloques solapados en archivo '{blocks[i].file}'",
                    )

    if trace is not None:
        trace.emit(
            "patch_attempt",
            files=sorted(files_touched_set),
            blocks=len(blocks),
            all_unique=True,
        )

    for fname in files_touched_set:
        content = file_contents[fname]
        file_blocks = [blk for blk in blocks if blk.file == fname]
        replacements = []
        for blk in file_blocks:
            pos = _find_all_positions(content, blk.search)[0]
            replacements.append((pos[0], blk))
        replacements.sort(key=lambda x: x[0], reverse=True)
        for _, blk in replacements:
            pos = _find_all_positions(content, blk.search)[0]
            content = content[: pos[0]] + blk.replace + content[pos[1] :]
        full = os.path.join(workspace_root, fname)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    sha = repo.commit_all(commit_message)

    for blk in blocks:
        full = os.path.join(workspace_root, blk.file)
        with open(full, "r", encoding="utf-8") as f:
            content_after = _normalize(f.read())
        if blk.replace not in content_after:
            if sha:
                repo.revert_head()
            return PatchResult(
                PatchStatus.VERIFY_FAILED,
                f"'{blk.file}': REPLACE no verificado tras escritura",
            )

    return PatchResult(
        PatchStatus.APPLIED,
        f"{len(blocks)} bloques aplicados",
        commit_sha=sha,
        files_touched=sorted(files_touched_set),
    )
