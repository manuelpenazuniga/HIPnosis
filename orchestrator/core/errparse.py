"""core/errparse.py — primitive (L2): compiler error parser.

Converts the raw stdout/stderr of ``hipcc`` / ``clang`` into a flat list
of :class:`BuildError` and rolls them up into :class:`ErrorGroup` keyed
by root-cause signature. This is the FIRST step of the build loop
(blueprint §6.1); groups are then handed to the classifier and patcher.

Layering: L2 primitive. Imports only ``core.schemas`` plus stdlib
(``re``, ``hashlib``, ``os``). No reference to ``phases``, ``oracle``,
``llm`` or ``state``.
"""

from __future__ import annotations

import hashlib
import os
import re

from core.schemas import BuildError, ErrorGroup


# clang / hipcc canonical line:
#     /path/to/file.cu:42:5: error: use of undeclared identifier 'foo'
#     /path/to/file.cu:42:5: fatal error: 'foo.h' file not found
# ``file`` cannot contain ':' or newlines; paths with colons (Windows,
# LDAP-style) are out of scope for the ROCm/Linux target.
_FILE_LINE_COL_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s+"
    r"(?P<sev>error|fatal error):\s+(?P<msg>.*)$"
)

# GNU ld / lld linker emission. NOT anchored to the line start because
# the line is usually prefixed by ``/usr/bin/ld:`` or ``ld.lld:``.
_LINKER_RE = re.compile(r"undefined reference to ")

# Tokens we mutate when computing a signature.
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_NUM_RE = re.compile(r"\d+")

# Single-quoted substrings are preserved verbatim by the normaliser.
# That is how the signature distinguishes ``'cudaMemcpy'`` from
# ``'cudaFree'`` even when the surrounding message is identical — and
# the entire reason two distinct unconverted-API errors are NOT
# collapsed into the same group at the signature level.
_QUOTED_RE = re.compile(r"'[^']*'")


def _normalize(msg: str) -> str:
    """Normalise a compiler error message for dedupe.

    Rules (blueprint §6.1):
      * numeric literals → ``#`` (so "expected 42 args" and
        "expected 7 args" collide on purpose)
      * hex addresses ``0x[0-9a-f]+`` → ``@`` (so memaddrs from
        runtime errors do not fork the signature)
      * single-quoted substrings are preserved verbatim, which keeps
        identifier-bearing errors like ``'cudaMemcpy'`` distinct from
        ``'cudaFree'`` even when the rest of the message is identical.
    """
    parts = _QUOTED_RE.split(msg)
    quoted = _QUOTED_RE.findall(msg)
    out: list[str] = []
    for i, part in enumerate(parts):
        chunk = _HEX_RE.sub("@", part)
        chunk = _NUM_RE.sub("#", chunk)
        out.append(chunk)
        if i < len(quoted):
            out.append(quoted[i])
    return "".join(out)


def _msg_signature(msg: str) -> str:
    """Signature of a message alone — used as the GROUP key.

    Different files manifesting the same root cause (the typical
    "broken header floods 40 TUs" cascade) share this key, even
    though their per-error signatures differ.
    """
    return hashlib.sha1(_normalize(msg).encode()).hexdigest()


def signature(file: str, msg: str) -> str:
    """Stable SHA1 of ``(basename(file), normalise(msg))``.

    The basename (not the full path) keeps the key stable across
    builds with different absolute roots (``/build/foo.cu`` vs
    ``/workspace/foo.cu`` are the SAME logical error for dedupe).
    """
    payload = f"{os.path.basename(file)}|{_normalize(msg)}"
    return hashlib.sha1(payload.encode()).hexdigest()


def parse(raw_output: str, max_errors: int = 30) -> list[BuildError]:
    """Parse hipcc/clang output into a list of :class:`BuildError`.

    The list is capped at ``max_errors`` (default 30, matching
    ``Config.max_errors_parsed``) — anything beyond is almost always
    cascade noise that the loop should ignore.

    Linker lines of the form ``undefined reference to 'foo'`` are
    captured as :class:`BuildError` with ``file="<link>"`` and
    ``line=0``, ``col=0`` (no source location available).
    """
    errors: list[BuildError] = []
    for line in raw_output.splitlines():
        m = _FILE_LINE_COL_RE.match(line)
        if m:
            file = m.group("file")
            errors.append(
                BuildError(
                    file=file,
                    line=int(m.group("line")),
                    col=int(m.group("col")) if m.group("col") is not None else 0,
                    message=m.group("msg"),
                    signature=signature(file, m.group("msg")),
                )
            )
            if len(errors) >= max_errors:
                break
            continue

        if _LINKER_RE.search(line):
            msg = line.strip()
            errors.append(
                BuildError(
                    file="<link>",
                    line=0,
                    col=0,
                    message=msg,
                    signature=signature("<link>", msg),
                )
            )
            if len(errors) >= max_errors:
                break

    return errors


def group(errors: list[BuildError]) -> list[ErrorGroup]:
    """Group errors by ROOT-CAUSE signature (= msg signature, file-agnostic).

    A broken header that surfaces the same error in 40 translation
    units collapses to ONE group; the loop then asks for a single fix
    on the first error's file and applies it.

    Groups are returned sorted by member count, DESC — the build loop
    (blueprint §6.4) always picks the highest-impact group first.
    """
    by_msg: dict[str, list[BuildError]] = {}
    for e in errors:
        by_msg.setdefault(_msg_signature(e.message), []).append(e)

    groups = [
        ErrorGroup(
            signature=msg_sig,
            errors=errs,
            klass=None,
            attempts=0,
            status="open",
        )
        for msg_sig, errs in by_msg.items()
    ]
    groups.sort(key=lambda g: len(g.errors), reverse=True)
    return groups
