"""core/attestation.py — Port Passport: atestación de procedencia verificable (L3).

"Cruzás la frontera con papeles" hecho literal: además del certificado legible,
HIPnosis emite ``HIPNOSIS_ATTESTATION.jsonl`` — una atestación machine-readable,
inspirada en in-toto/SLSA, con los digests SHA-256 del diff y del certificado,
los commits source/final, y el entorno (oracle_mode, GPU, veredicto).

Un verificador (el dashboard, o cualquiera con ``sha256sum``) recomputa el hash
del diff y lo compara con ``materials.diff.sha256``: si coinciden, el port es el
que la atestación declara; si se toca un byte, el hash cambia → TAMPERED.

Honestidad (audit codex, wow #2): esto es **procedencia SLSA nivel 1** — describe
qué produjo el artefacto, cómo y desde qué inputs. NO es L2: no hay firma ni
control plane protegido, así que la atestación NO se declara "authenticated".
Todos los números salen de código (F-17); jamás de un LLM.

Capa L3: importa ``hashlib``/``subprocess``/``json`` y ``core.schemas``. Sin
referencia a ``phases``, ``llm`` o ``state``.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Optional

ATTESTATION_FILENAME = "HIPNOSIS_ATTESTATION.jsonl"
ATTESTATION_TYPE = "https://hipnosis.dev/attestation/v1"
PREDICATE_TYPE = "https://hipnosis.dev/provenance/v1"
BUILDER_ID = "hipnosis://port-agent"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(repo_dir: str, *args: str, timeout: int = 15) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo_dir,
        capture_output=True, text=True, timeout=timeout,
    ).stdout


def workspace_diff(repo_dir: str) -> str:
    """El diff root..HEAD del workspace porteado (MISMA lógica que el endpoint
    ``/runs/{id}/diff``): así el digest de la atestación y el texto que el
    dashboard verifica son idénticos byte a byte."""
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        return ""
    try:
        roots = _git(repo_dir, "rev-list", "--max-parents=0", "HEAD").strip().splitlines()
        base = roots[0] if roots else "HEAD"
        return _git(repo_dir, "diff", base, "HEAD")
    except Exception:  # noqa: BLE001 — sin git utilizable, no hay materia que atestar
        return ""


def build_attestation(
    *,
    repo_url: str,
    repo_dir: str,
    oracle_mode: str,
    gpu_arch: str,
    verdict: str,
    counters: Any,
    wave64_findings: int = 0,
    rtol: Optional[float] = None,
    atol: Optional[float] = None,
    certificate_text: str = "",
    diff_text: Optional[str] = None,
) -> dict:
    """Construye la atestación (dict serializable). Digests computados acá (F-17).

    ``diff_text`` puede pasarse ya calculado (para que coincida exactamente con
    lo que el dashboard sirve); si es None, se obtiene de ``workspace_diff``.
    """
    if diff_text is None:
        diff_text = workspace_diff(repo_dir)

    source_commit = ""
    final_commit = ""
    branch = ""
    if os.path.isdir(os.path.join(repo_dir, ".git")):
        try:
            roots = _git(repo_dir, "rev-list", "--max-parents=0", "HEAD").strip().splitlines()
            source_commit = roots[0] if roots else ""
            final_commit = _git(repo_dir, "rev-parse", "HEAD").strip()
            branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").strip()
        except Exception:  # noqa: BLE001
            pass

    diff_bytes = len(diff_text.encode("utf-8"))
    cert_bytes = len(certificate_text.encode("utf-8"))

    result: dict[str, Any] = {"verdict": verdict}
    if counters is not None:
        result["errors_initial"] = getattr(counters, "errors_initial", 0)
        result["errors_final"] = getattr(counters, "errors_current", 0)
        result["iterations"] = getattr(counters, "iterations", 0)
    result["wave64_findings"] = wave64_findings
    if rtol is not None:
        result["numeric_rtol"] = rtol
    if atol is not None:
        result["numeric_atol"] = atol

    return {
        "_type": ATTESTATION_TYPE,
        "subject": {"repo_url": repo_url, "port_branch": branch},
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "builder": {"id": BUILDER_ID},
            "source": {"repo_url": repo_url, "commit": source_commit},
            "port": {"final_commit": final_commit, "branch": branch},
            "materials": {
                "diff": {"alg": "sha256", "digest": _sha256_text(diff_text), "bytes": diff_bytes},
                "certificate": {"alg": "sha256", "digest": _sha256_text(certificate_text), "bytes": cert_bytes},
            },
            "environment": {"oracle_mode": oracle_mode, "gpu_arch": gpu_arch},
            "result": result,
            # Honestidad explícita: L1, sin firma (audit codex).
            "provenance_level": (
                "SLSA-L1 (unsigned): describes inputs, build and environment; "
                "not cryptographically authenticated"
            ),
        },
    }


def write_attestation(attestation: dict, repo_dir: str) -> str:
    """Escribe la atestación como una línea JSON (.jsonl) y devuelve su path."""
    path = os.path.join(repo_dir, ATTESTATION_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(attestation, ensure_ascii=False, sort_keys=True))
        f.write("\n")
    return path
