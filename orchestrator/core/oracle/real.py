"""core/oracle/real.py — real subprocess oracle (L3), para el droplet MI300X.

Compila y ejecuta el repo objetivo con subprocess (hipcc/make) DENTRO del contenedor del
orquestador (sin docker-in-docker, §1). Mismo contrato que ``mock`` (INV-6): ninguna fase
distingue el modo. Conteo de errores CRUDO (líneas ': error:'), sin taxonomía (eso es L2 errparse).

⚠️ Se ejecuta solo en modo real (ORACLE_MODE=real) sobre hardware con ROCm. NO se testea en la
máquina de desarrollo sin GPU (blueprint AD-2, §12 M0): su interfaz está congelada y se valida en
el smoke test M0 (humano). Los tests de desarrollo usan ``mock``.
"""

from __future__ import annotations

import os
import re
import subprocess

from core.schemas import BuildResult, RunResult


# Conteo crudo de marcadores de error del compilador (idéntico criterio que mock.py, INV-6).
_ERROR_LINE = re.compile(r":\s*(?:fatal\s+)?error:")


def _count_error_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if _ERROR_LINE.search(line))


class RealOracle:
    """Oráculo real: subprocess sobre el workspace del repo objetivo.

    Parameters
    ----------
    repo_dir : ruta al workspace (repo clonado + hipificado).
    build_cmd : comando de compilación (del manifiesto §7.1, ya adaptado a hipcc por PORT).
    build_dir : subdir donde correr el build (relativo a repo_dir); default el propio repo_dir.
    build_timeout_s : tope de tiempo de compilación.
    """

    def __init__(
        self,
        repo_dir: str,
        build_cmd: str,
        build_dir: str = ".",
        build_timeout_s: int = 600,
    ) -> None:
        self._repo_dir = repo_dir
        self._build_cmd = build_cmd
        self._build_dir = os.path.join(repo_dir, build_dir)
        self._build_timeout_s = build_timeout_s

    def build(self) -> BuildResult:
        """Corre el comando de build; devuelve salida cruda + conteo crudo de errores."""
        try:
            proc = subprocess.run(
                self._build_cmd,
                shell=True,
                cwd=self._build_dir,
                capture_output=True,
                text=True,
                timeout=self._build_timeout_s,
            )
            raw = (proc.stdout or "") + (proc.stderr or "")
            returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            raw = (e.stdout or "") + (e.stderr or "") + "\nerror: build timeout expired\n"
            returncode = 124
        count = _count_error_lines(raw)
        # ok si el compilador salió 0 Y no hay marcadores de error (defensa en profundidad).
        ok = returncode == 0 and count == 0
        return BuildResult(ok=ok, count=count, raw_output=raw, returncode=returncode)

    def run(self, run_cmd: str | None = None, timeout_s: int = 120) -> RunResult:
        """Ejecuta el binario/self-check del benchmark; devuelve stdout + exit code."""
        if not run_cmd:
            return RunResult(ran=False, exit_code=-1, stdout="", timing=None)
        try:
            proc = subprocess.run(
                run_cmd,
                shell=True,
                cwd=self._repo_dir,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            return RunResult(
                ran=True,
                exit_code=proc.returncode,
                stdout=(proc.stdout or "") + (proc.stderr or ""),
                timing=None,
            )
        except subprocess.TimeoutExpired as e:
            return RunResult(
                ran=True,
                exit_code=124,
                stdout=(e.stdout or "") + "\n[timeout]\n",
                timing=None,
            )
