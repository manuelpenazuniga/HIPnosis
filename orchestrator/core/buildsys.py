"""core/buildsys.py — primitive (L2): deterministic build-system adaptation.

Adapts the target repo's build files from CUDA/nvcc to HIP/hipcc following the
exact rules in blueprint §6.0. Pure Python (stdlib only: ``re``, ``os``) so the
module is trivially testable without ROCm, without a compiler, without
subprocess. ``phases.port`` wraps these functions with the on-disk I/O and
the git commit; this module is the pure rule engine.

Layering: L2 primitive. Imports only stdlib. Does NOT import ``phases``,
``oracle``, ``llm`` or ``state``. Idempotent: running any of the ``adapt_*``
functions twice produces the same output as running them once — this is the
contract the build loop depends on when a single file is adapted by accident
twice (e.g. partial replay).

Rule summary (blueprint §6.0, F-02 + F-05 envelope):

    Makefile (HeCBench-style):
        CC = nvcc                -> CC = hipcc
        NVCC=...                 -> NVCC=hipcc    (defensive, harmless on HeCBench)
        CXX=nvcc                 -> CXX=hipcc     (some repos mix CXX with nvcc)
        -arch=sm_XX              -> (removed)
        -gencode <anything>      -> (removed)
        --use_fast_math          -> -ffast-math
        (insert, once) --offload-arch=<gpu_arch>

    CMake (best-effort, E13 fallback in the loop):
        find_package(CUDA ...)   -> (line removed; HIP doesn't need a find_package)
        enable_language(CUDA)    -> enable_language(HIP)
        (insert, once) set(CMAKE_HIP_ARCHITECTURES <gpu_arch>)

The CMake rules are intentionally narrow: the build loop handles "exotic"
CMake (E13) with the remote-tier LLM. The repos demo are Makefile-based
(F-03, F-07), so CMake is here for breadth, not depth.
"""

from __future__ import annotations

import os
import re


# Default architecture for AMD GPUs (MI300X = CDNA3 = gfx942). Callers may
# override via ``config.gpu_arch`` (INV-9: thresholds/arch from config).
_DEFAULT_GPU_ARCH = "gfx942"

# ---------------------------------------------------------------------------
# Makefile rule primitives (compiled once, reused).
# ---------------------------------------------------------------------------

# Variable assignments whose value should become ``hipcc``. Match the
# variable name (with optional spaces around ``=``) and the WHOLE RHS
# token that equals ``nvcc``. The RHS may be a longer expression like
# ``nvcc -O3``; we only rewrite the bare ``nvcc`` token, not the whole
# RHS — that would corrupt ``CC=nvcc -O3 -arch=sm_70`` into
# ``CC=hipcc -O3 -arch=sm_70`` (correct) and into ``CC=nvcc-other`` if
# someone was using a custom wrapper (we keep that untouched).
#
# Capture groups:
#   1: prefix (variable name + ``=`` + leading whitespace)
#   2: trailing whitespace (so the rewrite preserves formatting)
_NVCC_VAR_RE = re.compile(
    r"(^|\n)(?P<prefix>\s*(?:CC|CXX|NVCC)\s*=\s*)nvcc(?P<trail>\b)"
)

# `-arch=sm_XX` anywhere on a flag list. We delete the whole token
# including any leading whitespace so the line stays clean.
#
# Left guard: ``(?<![A-Za-z0-9_/.-])`` (not preceded by word char or
# path separator). The intent is to forbid ``-arch=sm_XX`` appearing
# in the MIDDLE of a path (e.g. ``myproject-arch=sm_70.cu``), while
# ALLOWING the realistic Makefile contexts:
#   * start of line, e.g. ``-arch=sm_70 -O3``
#   * after whitespace, e.g. ``CFLAGS=-O3 -arch=sm_70``
#   * after ``=``,    e.g. ``CFLAGS=-arch=sm_70 -O3``  (compact form)
#
# ``=`` is NOT in the forbidden set: it's the assignment operator in
# the compact form, never part of a path. We can't use the simpler
# ``(?<!\S)`` (not preceded by non-whitespace) because that would
# block the compact ``CFLAGS=-arch=sm_70`` form — and Python's re
# engine forbids variable-width lookbehinds, so the readable
# ``(?<=\s|^)`` doesn't compile either.
_ARCH_SM_RE = re.compile(r"(?<![A-Za-z0-9_/.-])-arch=sm_\d+\b")

# `-gencode ...`. CMake files and Makefiles use it; the typical value
# is a single comma-separated token like ``arch=compute_70,code=sm_70``,
# so the value has no internal whitespace. We delete the flag, any
# whitespace between it and the value, and the value itself. The
# pre-``\S*`` already covers the common case; the optional whitespace
# and value-tokens handle the split form (``-gencode arch=compute_70
# code=sm_70``) too, by eating whatever non-whitespace comes after the
# flag until the next whitespace gap. Same left guard as ``_ARCH_SM_RE``
# for the same reason.
_GENCDE_RE = re.compile(r"(?<![A-Za-z0-9_/.-])-gencode\b(?:\s+\S+)?")

# `--use_fast_math` -> `-ffast-math`. Single token substitution; hipcc
# doesn't accept nvcc's flag, and GCC's ``-ffast-math`` does the
# equivalent (and is what hipcc forwards to gcc for host code).
_USEM_FAST_MATH_RE = re.compile(r"(?<![A-Za-z0-9_/.-])--use_fast_math\b")

# Pre-existence check for the offload-arch flag. We don't want to
# insert a second copy if the repo already had one (idempotency).
_OFFLOAD_ARCH_RE = re.compile(r"(?<![A-Za-z0-9_/.-])--offload-arch=\S+")

# Makefile names we recognize as "the build file" for ``adapt_build``.
# Standard + lowercase variant + GNUmakefile (autotools convention).
_MAKEFILE_NAMES = ("Makefile", "makefile", "GNUmakefile")

# ---------------------------------------------------------------------------
# CMake rule primitives.
# ---------------------------------------------------------------------------

# find_package(CUDA ...) — whole line removal. The pattern matches the
# optional leading whitespace, ``find_package(``, ``CUDA`` and the
# rest of the line up to the closing paren. We delete the line and any
# trailing newline so the rewrite doesn't leave blank lines behind.
_CMAKE_FIND_CUDA_RE = re.compile(
    r"^[ \t]*find_package\s*\(\s*CUDA\b[^\)]*\)[^\n]*\n",
    re.MULTILINE,
)

# enable_language(CUDA) -> enable_language(HIP). Whitespace around the
# token is preserved so the resulting file is still readable.
_CMAKE_ENABLE_LANG_RE = re.compile(
    r"(enable_language\s*\(\s*)CUDA(\s*\))"
)

# Pre-existence check: if the CMake file already declares
# CMAKE_HIP_ARCHITECTURES (some projects do, e.g. mixed CUDA+HIP),
# we don't insert a second one (idempotency).
_CMAKE_HIP_ARCH_RE = re.compile(
    r"set\s*\(\s*CMAKE_HIP_ARCHITECTURES\b",
    re.IGNORECASE,
)

# CMake file name (CMake convention, case-sensitive on Linux but we
# match the canonical spelling only).
_CMAKE_FILENAME = "CMakeLists.txt"


# ---------------------------------------------------------------------------
# Makefile adaptation
# ---------------------------------------------------------------------------

def adapt_makefile(text: str, gpu_arch: str = _DEFAULT_GPU_ARCH) -> str:
    """Return ``text`` adapted from CUDA/nvcc to HIP/hipcc per §6.0.

    The function is purely text-in / text-out and idempotent. It does NOT
    parse the Makefile — that would require a real parser for marginal
    benefit, since the rules we need are local token substitutions.
    Anything we don't recognize is left untouched and surfaces in the
    build loop as E13 (build_system, remote tier).
    """
    arch = (gpu_arch or _DEFAULT_GPU_ARCH).strip() or _DEFAULT_GPU_ARCH

    # 1. Compiler variable rewrites. The pattern keeps the original
    #    prefix (variable name + ``=`` + leading whitespace) and
    #    trailing word boundary intact; only the literal ``nvcc`` is
    #    swapped for ``hipcc``. This means ``CC=nvcc -O3`` becomes
    #    ``CC=hipcc -O3`` (correct) and ``CXX=nvcc-12`` is left alone
    #    (a custom wrapper, no false positive).
    out = _NVCC_VAR_RE.sub(
        lambda m: f"{m.group('prefix')}hipcc{m.group('trail')}", text
    )

    # 2. Drop nvcc-only flags. Each ``re.sub`` returns the same string
    #    if there is no match, so this is safe on Makefiles that never
    #    had any of them.
    out = _ARCH_SM_RE.sub("", out)
    out = _GENCDE_RE.sub("", out)

    # 3. Flag rename: --use_fast_math (nvcc) -> -ffast-math (gcc/hipcc).
    out = _USEM_FAST_MATH_RE.sub("-ffast-math", out)

    # 4. Append --offload-arch=<arch> to the *first* occurrence of the
    #    CC/CXX/NVCC variable assignment, but ONLY if --offload-arch
    #    is not already present anywhere in the file. This mirrors
    #    what hipify-clang does, and it keeps the diff minimal and
    #    idempotent.
    if not _OFFLOAD_ARCH_RE.search(out):
        out = _inject_offload_arch(out, arch)

    return out


def _inject_offload_arch(text: str, arch: str) -> str:
    """Append ``--offload-arch=<arch>`` to the first CC/CXX/NVCC=hipcc
    line we can find. If none is present, the flag is inserted on its
    own line at the top of the file (graceful degradation — better
    than silently dropping the requirement).
    """
    flag = f"--offload-arch={arch}"
    m = re.search(
        r"(?P<head>^[^\n#]*?(?:CC|CXX|NVCC)\s*=\s*hipcc[^\n]*?)(?P<tail>[ \t]*)",
        text,
        re.MULTILINE,
    )
    if m:
        head = m.group("head")
        tail = m.group("tail")
        # If the line already has another token after ``hipcc``, glue
        # with a single space. Otherwise just append. Idempotent
        # because we early-return if --offload-arch is already there.
        if head.rstrip().endswith("hipcc"):
            replacement = f"{head.rstrip()} {flag}"
        else:
            replacement = f"{head}{flag}"
        # Reconstruct the line preserving the trailing newline(s).
        return text[: m.start()] + replacement + text[m.end():]

    # No compiler variable found at all — emit a defensive top-of-file
    # assignment so the requirement is at least recorded. A reviewer
    # can move it where it belongs. (CMake-only projects land here
    # too, but they have their own rule in adapt_cmake — this is the
    # Makefile fallback.)
    return f"{flag}\n" + text


# ---------------------------------------------------------------------------
# CMake adaptation
# ---------------------------------------------------------------------------

def adapt_cmake(text: str, gpu_arch: str = _DEFAULT_GPU_ARCH) -> str:
    """Return ``text`` adapted from CUDA to HIP per §6.0 (best-effort).

    This is intentionally narrow. Exotic CMake flows (CUDA-as-language
    property, custom commands, per-target languages) are routed to the
    E13 build_system class in the build loop — that is the explicit
    blueprint contract: "No intentar cubrir todo CMake
    determinísticamente." §6.0.

    The rewrite is idempotent. Running it twice on a file already
    adapted by us is a no-op: ``find_package(CUDA)`` is gone, so the
    removal regex doesn't match; ``enable_language(HIP)`` is unchanged
    by ``enable_language(CUDA) -> enable_language(HIP)``; the
    CMAKE_HIP_ARCHITECTURES pre-check skips the second insert.
    """
    arch = (gpu_arch or _DEFAULT_GPU_ARCH).strip() or _DEFAULT_GPU_ARCH

    out = _CMAKE_FIND_CUDA_RE.sub("", text)
    out = _CMAKE_ENABLE_LANG_RE.sub(r"\1HIP\2", out)

    if not _CMAKE_HIP_ARCH_RE.search(out):
        # Insert right after the ``project(...)`` call when present
        # (idiomatic placement: project comes first, then per-tool
        # config). Otherwise prepend to the top of the file.
        out = _inject_cmake_arch(out, arch)

    return out


def _inject_cmake_arch(text: str, arch: str) -> str:
    """Insert ``set(CMAKE_HIP_ARCHITECTURES <arch>)`` near the top."""
    line = f"set(CMAKE_HIP_ARCHITECTURES {arch})"
    m = re.search(r"^\s*project\s*\([^)]*\)[^\n]*\n", text, re.MULTILINE)
    if m:
        return text[: m.end()] + line + "\n" + text[m.end():]
    return line + "\n" + text


# ---------------------------------------------------------------------------
# On-disk adaptation
# ---------------------------------------------------------------------------

def _build_file_candidates(repo_dir: str, build_system: str) -> list[str]:
    """Absolute paths of build files we'll try to adapt, in stable order.

    Missing files are silently skipped (we filter by an exact-case
    existence check). The list is in priority order — the FIRST
    existing file is the one we return, but we also scan sibling
    variants so a repo with ``GNUmakefile`` and no ``Makefile`` still
    works.

    Note: ``os.path.isfile`` is case-INsensitive on macOS / Windows
    default filesystems, which means a workspace that ONLY has
    ``makefile`` (lowercase, autotools style) would ALSO match
    ``Makefile`` here. We force case-sensitive matching by listing
    the actual directory entries and comparing names verbatim —
    otherwise on a HFS+/APFS-default volume we'd return a path the
    test fixture never actually wrote.
    """
    if build_system == "make":
        names = _MAKEFILE_NAMES
    elif build_system == "cmake":
        names = (_CMAKE_FILENAME,)
    else:
        # Unknown build system — nothing to adapt at this layer. The
        # build loop's E13 rule will surface the real failure.
        return []

    try:
        present = set(os.listdir(repo_dir))
    except OSError:
        return []

    return [
        os.path.join(repo_dir, n)
        for n in names
        if n in present and os.path.isfile(os.path.join(repo_dir, n))
    ]


def adapt_build(
    repo_dir: str,
    build_system: str,
    gpu_arch: str = _DEFAULT_GPU_ARCH,
) -> list[str]:
    """Adapt the build file(s) of ``repo_dir`` in-place and return their paths.

    The function:

      1. Looks for the build file(s) appropriate for ``build_system``
         (``"make"`` or ``"cmake"``).
      2. Reads each, calls the corresponding ``adapt_makefile`` /
         ``adapt_cmake``.
      3. Writes the adapted text back atomically (overwrite the same
         path — the pipeline is the only writer, and ``git`` is the
         audit trail).
      4. Returns the list of files actually modified (only files whose
         content changed; unchanged files are NOT included so the
         caller can avoid no-op commits in the future).

    The function is filesystem-safe:

      * If no build file is found, returns ``[]`` without raising.
      * If the build file is read-only or unwritable, the underlying
        ``open(..., "w")`` raises ``OSError`` — the pipeline treats
        that as a real failure (per INV-3: all writes to the target
        repo are auditable, and silently swallowing I/O errors would
        hide the very issue the trace exists to surface).
    """
    arch = (gpu_arch or _DEFAULT_GPU_ARCH).strip() or _DEFAULT_GPU_ARCH
    candidates = _build_file_candidates(repo_dir, build_system)

    modified: list[str] = []
    for path in candidates:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        if build_system == "make":
            adapted = adapt_makefile(original, gpu_arch=arch)
        else:  # "cmake" — other values are filtered above
            adapted = adapt_cmake(original, gpu_arch=arch)

        if adapted != original:
            with open(path, "w", encoding="utf-8") as f:
                f.write(adapted)
            modified.append(path)

    return modified
