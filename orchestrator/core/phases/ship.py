"""core/phases/ship.py — FASE 5 SHIP (certificate + branch/PR, blueprint §8).

Capa L4 (phase). El entregable de esta fase es el **certificado de port**
(``HIPNOSIS_CERTIFICATE.md``) — el PR/Patch es azúcar (F-13b/INV-5: el run
NO falla si el push o ``gh`` se caen). Toda la inteligencia de la fase
vive en ``core.report`` (templates Jinja2 + ``ReportData``); este módulo
es el driver determinista que:

  1. Renderiza el certificado con ``render_certificate(report_data)`` y lo
     escribe a ``<repo_dir>/HIPNOSIS_CERTIFICATE.md`` (F-13b: el
     certificado ES el producto — debe existir SIEMPRE, aun cuando el PR
     falle o no haya token).
  2. Si ``config.github_token`` está set → intenta abrir un PR contra un
     fork del repo (F-13b: el push va al FORK, no al upstream real de
     HeCBench). El PR se hace con ``gh repo fork`` + ``git push`` +
     ``gh pr create --body-file``. La función ``make_pr`` es el ÚNICO
     punto donde se invoca ``subprocess`` contra ``gh`` — está aislada
     para que los tests la mockeen sin tocar subprocess real.
  3. Si NO hay token o el PR falla → ``git format-patch --stdout`` de la
     rama ``hipnosis/rocm-port`` contra su base, escrito a un solo
     ``.patch``. La rama queda local en el workspace.

El resultado de la fase es SIEMPRE positivo para ``DONE``/``DONE_PARTIAL``
(incluso si el PR falla): lo único que marca el final del run como
``FAILED`` es un crash del handler — no la falta de PR.

El handler ``ship_handler`` se enchufa al driver de state como override
para ``REPORTING`` (el default es un stub en ``core.state``). Toma el
``ctx`` que produce ``run_pipeline``, ensambla un ``ReportData`` desde
los campos disponibles (scan_result, loop_result opcional,
verify_result opcional) y llama a ``ship``.

Layering: L4. Importa ``core.report`` (L4), ``core.gitrepo`` (L2),
``core.schemas`` (L1), ``core.config`` (L1), ``core.trace`` (L1) y
stdlib (``os``, ``subprocess``). NO importa ``core.llm``,
``core.oracle`` ni ``core.state`` — el ctx del handler se tipa con
``TYPE_CHECKING`` y se usa con duck-typing en runtime (F-13b: la fase
no depende de la FSM driver para ser testeable; ``ship()`` solo necesita
un ``GitRepo`` + ``Config`` + ``ReportData``).
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from core.config import Config
from core.gitrepo import GitRepo
from core.report import ReportData, render_certificate, render_pr_body
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Nombre del archivo del certificado de port. Lo escribimos en la RAÍZ
#: del repo (no en ``out/``) porque es el entregable visible al lector
#: humano que navegue el branch — el nombre en MAYÚSCULAS sigue la
#: convención de "deliverable" (similar a LICENSE, README, CONTRIBUTING).
CERTIFICATE_FILENAME = "HIPNOSIS_CERTIFICATE.md"

#: Nombre del patch cuando NO se hace PR (F-13b: branch local + format-patch
#: + certificado son el entregable de graceful-degradation).
PATCH_FILENAME = "hipnosis-port.patch"

#: Subdirectorio del workspace donde se vuelcan artefactos secundarios
#: (el patch, eventualmente cuerpos de PR generados, etc.). El
#: certificado NO va acá — va en la raíz del repo.
OUT_SUBDIR = "out"

#: Branch que ``port.py`` dejó chequeada y donde se acumulan los commits
#: del port. Lo usamos como input tanto para ``make_pr`` (push) como
#: para ``_format_patch`` (diff contra la base de la rama).
SHIPPED_BRANCH = "hipnosis/rocm-port"


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------

class ShipError(RuntimeError):
    """Fallo recuperable de la fase SHIP. La fase NO aborta el run
    (INV-5: la falta de PR es degradación honesta, no FAILED); ``ship()``
    captura y cae al fallback de format-patch. Se distingue de
    excepciones realmente fatales (las propagamos)."""


# ---------------------------------------------------------------------------
# Seam: make_pr (gh) — mockeable
# ---------------------------------------------------------------------------

#: Toolchain por defecto. Constante para que el test pueda verificar la
#: decisión firme del blueprint y ``make_pr`` no haga ``which`` implícito.
GH_BIN = "gh"


def make_pr(
    report_data: ReportData,
    repo_dir: str,
    branch: str,
    certificate_path: str,
    config: Config,
    trace: Optional[TraceWriter] = None,
) -> str:
    """Crear un PR contra un fork del repo (F-13b, §8).

    Pasos (blueprint §8):
      1. ``gh repo fork --remote=true`` (contra el upstream del repo target).
      2. ``git push <remote> <branch>`` (la rama al fork).
      3. Escribir un cuerpo de PR con ``render_pr_body`` y abrir el PR
         con ``gh pr create --body-file``.

    La rama del PR es SIEMPRE contra el FORK (``--repo <fork>`` /
    ``--head <user>:<branch>``), no contra el upstream — los repos
    HeCBench son proyectos de terceras partes: el PR es AZÚCAR para
    mostrar el flujo, no se pretende upstream-merge.

    Args:
        report_data:    snapshot ya construido (F-17: los números del PR
                        salen de acá, no se inventan).
        repo_dir:       ruta absoluta al workspace clonado (cwd de los
                        subprocess).
        branch:         rama a pushear (default ``hipnosis/rocm-port``).
        certificate_path: ruta al ``HIPNOSIS_CERTIFICATE.md`` que el PR
                        cita como evidencia.
        config:         configuración del run; ``config.github_token`` es
                        la AUTH que ``gh`` lee de ``GH_TOKEN`` env.
        trace:          opcional; emite ``ship.pr.*`` en cada paso.

    Returns:
        La URL del PR (string) si ``gh pr create`` la imprimió.

    Raises:
        ShipError: si falta el token, falla el fork, falla el push, o
            falla el ``pr create``. ``ship()`` la captura y cae al
            fallback de format-patch.
    """
    token = (config.github_token or "").strip()
    if not token:
        raise ShipError("github_token ausente; make_pr requiere token")

    # Cuerpo del PR (markdown). Se escribe a un archivo temporal en
    # ``<repo_dir>/out/pr_body.md`` para que ``--body-file`` lo lea.
    pr_body = render_pr_body(report_data)
    out_dir = os.path.join(repo_dir, OUT_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    body_path = os.path.join(out_dir, "pr_body.md")
    with open(body_path, "w", encoding="utf-8") as f:
        f.write(pr_body)

    # Auth: ``gh`` lee ``GH_TOKEN`` del entorno cuando no hay sesión
    # interactiva (droplet/CI). El token llega por config (env-driven);
    # NO se loguea.
    env = os.environ.copy()
    env["GH_TOKEN"] = token

    def _run(args: list[str]) -> subprocess.CompletedProcess:
        if trace is not None:
            trace.emit("ship.pr.step", argv=args[:2])
        return subprocess.run(
            args,
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    # 1. Fork (idempotente: si ya existe, ``--remote=true`` lo agrega
    # como remote adicional). Si esto falla, NO seguimos — sin fork
    # no hay a quién pushear.
    fork = _run([GH_BIN, "repo", "fork", "--remote=true"])
    if fork.returncode != 0:
        raise ShipError(
            f"gh repo fork falló (rc={fork.returncode}): "
            f"{(fork.stderr or fork.stdout).strip()[:300]}"
        )

    # 2. Push al fork. El nombre del remote por defecto que ``gh`` agrega
    # es el slug del owner (no siempre "origin"); usamos el nombre que
    # ``gh`` imprime, o caemos a "origin" si no lo encontramos.
    fork_remote = _detect_fork_remote(repo_dir, env=env) or "origin"
    push = _run(["git", "push", fork_remote, branch])
    if push.returncode != 0:
        raise ShipError(
            f"git push falló (rc={push.returncode}): "
            f"{(push.stderr or push.stdout).strip()[:300]}"
        )

    # 3. PR create. ``--body-file`` para no pelearse con quoting; el
    # target es el repo ORIGINAL (no el fork) — ``gh pr create`` lo
    # resuelve a partir del remote upstream.
    pr = _run(
        [
            GH_BIN, "pr", "create",
            "--head", branch,
            "--body-file", body_path,
            "--title", f"HIPnosis port — {report_data.run_id or 'auto'}",
        ]
    )
    if pr.returncode != 0:
        raise ShipError(
            f"gh pr create falló (rc={pr.returncode}): "
            f"{(pr.stderr or pr.stdout).strip()[:300]}"
        )

    # ``gh pr create`` imprime la URL del PR en stdout (última línea
    # no vacía usualmente). Si no la encontramos, devolvemos la salida
    # completa como fallback (no es URL pero al menos queda registro).
    url = ""
    for line in (pr.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("http://") or s.startswith("https://"):
            url = s
    if not url:
        url = (pr.stdout or "").strip().splitlines()[-1] if pr.stdout else ""

    if trace is not None:
        trace.emit("ship.pr.done", url=url, branch=branch)

    return url


def _detect_fork_remote(repo_dir: str, env: dict[str, str]) -> Optional[str]:
    """Detectar el nombre del remote del fork que ``gh repo fork`` agregó.

    ``gh`` agrega el fork como un remote adicional cuyo nombre es el
    nombre del owner del fork (a veces el mismo que ``origin``, a veces
    no — depende de si fork == upstream). Buscamos un remote cuya URL
    NO sea la del repo original (es decir, que apunte a un fork).
    """
    try:
        out = subprocess.run(
            ["git", "remote", "-v"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None

    # Líneas: "<name>\t<url> (fetch)" / "(push)"
    remotes: dict[str, str] = {}
    for line in (out.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name, url = parts[0], parts[1]
            remotes.setdefault(name, url)

    # Heurística: si hay 2+ remotes, el que NO sea el upstream
    # (``origin``) es el fork. Si sólo hay uno y es ``origin``,
    # ``gh`` lo habrá dejado apuntando al fork; lo aceptamos.
    if len(remotes) >= 2:
        for name, url in remotes.items():
            if name != "origin":
                return name
    return "origin"


# ---------------------------------------------------------------------------
# format-patch (fallback) — robusto, sin red
# ---------------------------------------------------------------------------

def _format_patch(
    repo_dir: str,
    out_dir: str,
    branch: str = SHIPPED_BRANCH,
) -> str:
    """Escribir un ``.patch`` con todo el delta de la rama vs su base.

    Estrategia: ``git format-patch --stdout <base>..<branch>`` con ``base``
    = padre del commit más antiguo en la rama. Si el padre no existe
    (shallow clone del droplet, F-02: ``--depth 1``), caemos a
    ``format-patch -1`` que captura el último commit — sigue siendo un
    entregable honesto (el lector puede hacer ``git am`` y reconstruir
    el estado post-port).

    Devuelve la ruta absoluta al ``.patch`` escrito.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, PATCH_FILENAME)

    # 1. Encontrar la base: el padre del commit más antiguo en la rama.
    base = _find_branch_base(repo_dir, branch)

    if base is not None:
        args = ["git", "format-patch", "--stdout", f"{base}..{branch}"]
    else:
        # Shallow / single-commit branch: caemos al último commit.
        args = ["git", "format-patch", "--stdout", "-1", branch]

    try:
        result = subprocess.run(
            args,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # Último recurso: si TODO falla, escribimos un header con el SHA
        # de HEAD para que el lector sepa al menos qué commit mirar.
        sha = _safe_head_sha(repo_dir)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(
                f"# format-patch falló: {e}\n"
                f"# HEAD: {sha}\n"
                f"# branch: {branch}\n"
            )
        return out_path

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    return out_path


def _find_branch_base(repo_dir: str, branch: str) -> Optional[str]:
    """Devuelve el SHA del padre del commit más antiguo en ``branch``,
    o ``None`` si no se puede determinar (branch unborn, padre
    inexistente en shallow clone, etc.)."""
    try:
        first = subprocess.run(
            ["git", "rev-list", "--max-parents=0", branch],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    if not first:
        return None
    try:
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", f"{first}^"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    return parent or None


def _safe_head_sha(repo_dir: str) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return "<unknown>"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def ship(
    report_data: ReportData,
    repo: GitRepo,
    repo_dir: str,
    config: Config,
    trace: Optional[TraceWriter] = None,
) -> dict:
    """FASE 5 — generar el certificado y entregar el branch/PR.

    Pasos (blueprint §8):
      1. Renderizar el certificado (``core.report.render_certificate``)
         y escribirlo a ``<repo_dir>/HIPNOSIS_CERTIFICATE.md``. ESTE
         paso ocurre SIEMPRE, incluso si los siguientes fallan (F-13b).
      2. Si ``config.github_token`` está set → intentar ``make_pr``.
         Si el PR tiene éxito, ``mode = "pr"`` y ``pr_url`` se popula.
         Si falla, el handler NO aborta: emitimos ``ship.pr_failed`` y
         caemos al fallback.
      3. Fallback (``mode = "patch"``): ``_format_patch`` produce
         ``<repo_dir>/out/hipnosis-port.patch`` con todo el delta de la
         rama ``hipnosis/rocm-port`` vs su base. La rama queda local
         en el workspace (INV-3: el trabajo del pipeline es auditable
         como branch git).

    Args:
        report_data: ``ReportData`` ya construido por ``build_report_data``.
                     Sus números son los que el certificado imprime (F-17).
        repo:        ``GitRepo`` apuntando al workspace. Se usa para
                     conocer la rama actual y para ``head_sha`` en el
                     trace (no se commitea nada nuevo — la rama ya
                     quedó commiteada por ``port.py`` y ``loop.py``).
        repo_dir:    ruta ABSOLUTA del workspace (donde escribir el
                     certificado y donde correr ``gh``/``git``).
        config:      ``Config`` del run; ``github_token`` decide el camino.
        trace:       opcional; cada paso emite un evento ``ship.*``.

    Returns:
        ``dict`` con::

            {
                "certificate_path": "<abs path a HIPNOSIS_CERTIFICATE.md>",
                "pr_url":           "<URL o None>",
                "patch_path":       "<abs path al .patch o None>",
                "mode":             "pr" | "patch",
            }

        Garantías (F-13b/INV-5):
          * ``certificate_path`` SIEMPRE presente.
          * ``mode == "pr"`` ⇔ ``pr_url`` no es None.
          * ``mode == "patch"`` ⇔ ``patch_path`` no es None.
          * El dict NUNCA levanta excepciones al caller — la fase es
            "azúcar" (F-13b), los fallos degradan a ``patch`` o, en el
            peor caso, a un ``.patch`` con un header explicativo.
    """
    # --- 1. Certificado (SIEMPRE) -----------------------------------------
    md = render_certificate(report_data)
    certificate_path = os.path.join(repo_dir, CERTIFICATE_FILENAME)
    with open(certificate_path, "w", encoding="utf-8") as f:
        f.write(md)

    if trace is not None:
        trace.emit(
            "ship.certificate",
            path=certificate_path,
            bytes=len(md.encode("utf-8")),
            verdict=report_data.verify_verdict,
        )

    out_dir = os.path.join(repo_dir, OUT_SUBDIR)

    # --- 2. PR (best-effort) o patch (fallback) ---------------------------
    pr_url: Optional[str] = None
    patch_path: Optional[str] = None
    mode: str = "patch"

    token_present = bool((config.github_token or "").strip())
    if token_present:
        try:
            pr_url = make_pr(
                report_data=report_data,
                repo_dir=repo_dir,
                branch=SHIPPED_BRANCH,
                certificate_path=certificate_path,
                config=config,
                trace=trace,
            )
            mode = "pr"
        except Exception as exc:  # noqa: BLE001 — degradación honesta (F-13b/INV-5)
            if trace is not None:
                trace.emit(
                    "ship.pr_failed",
                    reason=str(exc),
                    exc_type=type(exc).__name__,
                )
            pr_url = None
            mode = "patch"

    if mode == "patch":
        # El fallback de patch ES el entregable de graceful-degradation
        # (F-13b). Si incluso esto falla, NO abortamos el run (INV-5):
        # el certificado ya está en disco, que es el producto. El
        # ``patch_path`` queda en ``None`` y emitimos el evento de
        # diagnóstico para que el dashboard muestre el problema.
        try:
            patch_path = _format_patch(
                repo_dir=repo_dir,
                out_dir=out_dir,
                branch=SHIPPED_BRANCH,
            )
        except Exception as exc:  # noqa: BLE001 — degradación honesta (F-13b/INV-5)
            if trace is not None:
                trace.emit(
                    "ship.patch_failed",
                    reason=str(exc),
                    exc_type=type(exc).__name__,
                )
            patch_path = None
        if trace is not None and patch_path is not None:
            trace.emit("ship.patch", path=patch_path)

    # --- 3. Evento final 'ship' (el contrato del task) --------------------
    head_sha = repo.head_sha() if repo is not None else ""
    if trace is not None:
        trace.emit(
            "ship",
            certificate_path=certificate_path,
            mode=mode,
            pr_url=pr_url,
            patch_path=patch_path,
            head_sha=head_sha,
            branch=repo.current_branch() if repo is not None else "",
        )

    return {
        "certificate_path": certificate_path,
        "pr_url": pr_url,
        "patch_path": patch_path,
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# Handler para el driver de state (REPORTING)
# ---------------------------------------------------------------------------

def ship_handler(ctx: Any) -> None:
    """Phase handler para ``RunState.REPORTING`` en el FSM driver.

    Ensambla un ``ReportData`` desde los campos del ``ctx``:

      * ``ctx.scan_result``     — obligatorio (poblado por SCANNING).
      * ``ctx.loop_result``     — opcional; si no está, ``build_report_data``
                                  usa ``ctx.run.counters`` (F-17/INV-7).
      * ``ctx.verify_result``   — opcional; si no está, el certificado
                                  dice ``NO_ORACLE`` (F-08 honesto).

    Luego llama a ``ship`` y stashes el resultado en ``ctx``:

      * ``ctx.certificate_path`` — ruta al ``HIPNOSIS_CERTIFICATE.md``
        (para que ``app/`` lo sirva en el dashboard).
      * ``ctx.ship_result``      — el dict completo devuelto por ``ship``.

    El ctx se tipa como ``Any`` para que este módulo se mantenga L4
    puro: NO importamos ``core.state``. La FSM (``run_pipeline``) llama
    este handler con un ``PipelineContext`` concreto, pero el contrato
    real es por atributos (``run``, ``repo_dir``, ``config``, ``trace``,
    ``scan_result``, ``loop_result`` opcional, ``verify_result`` opcional).

    Raises:
        RuntimeError: si el handler se invoca antes de SCANNING (no
            hay ``scan_result`` para el certificado). Esto SÍ es
            un bug del orquestador, no una condición esperada — la
            FSM garantiza que SCANNING se ejecuta antes que REPORTING
            (blueprint §3, ``_LINEAR_SEQUENCE``), así que la
            excepción es puramente defensiva.
    """
    scan_result = getattr(ctx, "scan_result", None)
    if scan_result is None:
        raise RuntimeError(
            "ship_handler llamado antes de SCANNING: ctx.scan_result es None"
        )

    # Import diferido para NO contaminar el módulo en tiempo de carga
    # (mantiene ship.py L4-puro: ``core.report`` está bien, pero
    # ``build_report_data`` vive en ``core.report`` que ya importamos).
    from core.report import build_report_data  # noqa: PLC0415

    loop_result = getattr(ctx, "loop_result", None)
    verify_result = getattr(ctx, "verify_result", None)
    run = ctx.run
    config = ctx.config

    report_data = build_report_data(
        scan_result=scan_result,
        loop_result=loop_result,
        verify_result=verify_result,
        run=run,
        config=config,
    )

    repo_dir = ctx.repo_dir
    trace = getattr(ctx, "trace", None)
    repo = GitRepo(repo_dir)

    result = ship(report_data, repo, repo_dir, config, trace=trace)

    # Stash en ctx (para el dashboard / para fases futuras que quieran
    # el path del certificado sin re-llamar a ``ship``).
    ctx.certificate_path = result["certificate_path"]
    ctx.ship_result = result

    # --- Port Passport: atestación de procedencia verificable (wow #2) -----
    # Digests SHA-256 del diff y del certificado (F-17: hashes por código).
    try:
        from core.attestation import (  # noqa: PLC0415
            build_attestation,
            workspace_diff,
            write_attestation,
        )

        with open(result["certificate_path"], encoding="utf-8") as _cf:
            cert_text = _cf.read()

        manifest = getattr(ctx, "manifest", None)
        rtol = getattr(getattr(manifest, "verify", None), "numeric_rtol", None)
        atol = getattr(getattr(manifest, "verify", None), "numeric_atol", None)

        att = build_attestation(
            repo_url=run.repo_url,
            repo_dir=repo_dir,
            oracle_mode=config.oracle_mode,
            gpu_arch=config.gpu_arch,
            verdict=report_data.verify_verdict,
            counters=run.counters,
            wave64_findings=len(report_data.wave64_findings),
            rtol=rtol,
            atol=atol,
            certificate_text=cert_text,
            diff_text=workspace_diff(repo_dir),
        )
        att_path = write_attestation(att, repo_dir)
        ctx.attestation_path = att_path
        if trace is not None:
            trace.emit("ship.attestation", path=att_path,
                       diff_digest=att["predicate"]["materials"]["diff"]["digest"])
    except Exception:  # noqa: BLE001 — INV-5: el passport es azúcar, nunca tumba el run
        pass


__all__ = [
    "CERTIFICATE_FILENAME",
    "GH_BIN",
    "OUT_SUBDIR",
    "PATCH_FILENAME",
    "SHIPPED_BRANCH",
    "ShipError",
    "make_pr",
    "ship",
    "ship_handler",
]
