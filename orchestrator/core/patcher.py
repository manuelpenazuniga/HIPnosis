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
    PROTECTED = "protected"


# Paths que NINGÚN parche puede tocar, jamás (§0.2: los oráculos no se negocian).
# El contenido del repo objetivo y la salida del compilador son INPUT NO CONFIABLE
# que termina dentro de prompts LLM; si una inyección convence al modelo de "arreglar"
# el manifiesto o el workflow de CI, el rechazo tiene que ser mecánico, acá.
# Entradas que terminan en "/" protegen el directorio completo (prefijo).
PROTECTED_ALWAYS: tuple[str, ...] = (
    "hipnosis.yaml",
    ".hipnosis/",
    ".github/",
)


def is_protected(rel_path: str, extra: tuple[str, ...] = ()) -> bool:
    """True si *rel_path* (relativo al workspace, separador ``/``) es intocable.

    Compara contra :data:`PROTECTED_ALWAYS` + ``extra`` (p.ej. el golden file
    que declara el manifiesto). Match exacto para archivos; prefijo para
    entradas que terminan en ``/``.
    """
    def _norm(p: str) -> str:
        p = p.replace(os.sep, "/")
        while p.startswith("./"):
            p = p[2:]
        return p

    norm = _norm(rel_path)
    for entry in PROTECTED_ALWAYS + tuple(extra):
        if not entry:
            continue
        e = _norm(entry)
        if e.endswith("/"):
            if norm.startswith(e) or norm == e.rstrip("/"):
                return True
        elif norm == e:
            return True
    return False


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

# Marcadores estructurales SOLO como línea completa (anclados). Un marcador que
# aparezca DENTRO del contenido de un bloque (p.ej. un string C `"<<<<<<< SEARCH"`)
# NO es estructural — por eso el chequeo se hace sobre el RESIDUO (el texto FUERA de
# los bloques ya matcheados), no sobre todo el parche. (Corrige la regresión del
# re-audit: contar marcadores globalmente rechazaba parches válidos con markers en el código.)
_DANGLING_MARKER_RE = re.compile(
    r"(?m)^[ \t]*(?:<<<<<<<[ \t]+SEARCH|>>>>>>>[ \t]+REPLACE|=======)[ \t]*$"
)


def parse_blocks(patch_text: str) -> list[Block]:
    """Parse SEARCH/REPLACE blocks. Returns ``[]`` if a malformed/truncated block
    leaves a DANGLING structural marker outside any well-formed block (Critical fix
    #1: never silently ignore a partially-formed block), sin falso-rechazar parches
    cuyo contenido contenga texto parecido a un marcador (regresión del re-audit)."""
    normalized = patch_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    spans: list[tuple[int, int]] = []
    for m in _BLOCK_RE.finditer(normalized):
        blocks.append(Block(file=m.group(1).strip(), search=m.group(2), replace=m.group(3)))
        spans.append((m.start(), m.end()))

    # Residuo = el parche con los bloques bien formados removidos. Cualquier marcador
    # estructural (línea completa) que sobreviva ahí es un bloque truncado/malformado.
    residue_parts: list[str] = []
    last = 0
    for start, end in spans:
        residue_parts.append(normalized[last:start])
        last = end
    residue_parts.append(normalized[last:])
    residue = "".join(residue_parts)

    if _DANGLING_MARKER_RE.search(residue):
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
    protected_paths: tuple[str, ...] = (),
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
        rel = os.path.relpath(cp, str(Path(workspace_root).resolve()))
        if is_protected(rel, protected_paths):
            if trace is not None:
                trace.emit("patch_rejected", reason="protected_path", file=rel)
            return PatchResult(
                PatchStatus.PROTECTED,
                f"path protegido (oráculo/CI intocable): '{blk.file}'",
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
