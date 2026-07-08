Trabajás en el worktree actual (rama spike/t17-ship). Implementá SOLO esta tarea.

--- TAREA T17: core/phases/ship.py — FASE 5 SHIP (§8): certificado + branch/PR ---
Capa L4. Importa core.report (existe), core.gitrepo, core.schemas, core.config, core.trace, stdlib
(subprocess para gh/git format-patch). NO importa llm/oracle/state.

ARCHIVO: orchestrator/core/phases/ship.py    TEST: orchestrator/tests/test_ship.py

Contrato:
    def ship(report_data, repo, repo_dir, config, trace=None) -> dict:
        # 1. Generar el certificado: md = core.report.render_certificate(report_data). Escribirlo a
        #    <repo_dir>/HIPNOSIS_CERTIFICATE.md (o a un out_dir). También render_portability si querés.
        # 2. Entregable git (F-13b): si config.github_token → intentar gh fork + push branch + gh pr
        #    create --body-file (contra el FORK, no upstream). Si NO hay token o gh falla → git
        #    format-patch de la rama hipnosis/rocm-port a un .patch + dejar la branch local.
        #    ⚠️ En mock/test NO ejecutes gh de verdad: encapsulá la parte de PR en una función mockeable
        #    (make_pr) que en test se stubbea. El certificado SÍ se genera siempre.
        # 3. Devolver dict {certificate_path, patch_path o pr_url, mode}. Emitir evento "ship" al trace.
    def ship_handler(ctx) -> None:
        # handler de fase REPORTING para el driver de state: arma ReportData del ctx (scan/loop/verify),
        # llama ship, guarda el path del certificado en ctx/trace.

El PR es AZÚCAR (F-13b): el certificado es el producto. NO falles el run si el PR falla (INV-5).

Test test_ship.py (SIN gh real):
- ship con un ReportData mínimo + repo temporal → genera HIPNOSIS_CERTIFICATE.md con el verdict y las
  secciones; devuelve certificate_path.
- sin github_token → produce un .patch (format-patch) o al menos deja la branch; mode="patch".
- make_pr mockeado → no ejecuta gh real.

Criterios: pytest verde; el certificado se genera SIEMPRE; PR mockeable (no gh real en test); NO importa llm/oracle/state.
Al terminar: COMMIT ("feat(phases): ship — certificado + branch/PR (§8) + tests"). Respuesta CORTA. Bloqueo: 'BLOCKED |...'.
ENTORNO: venv en /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python. El contrato base ya existe en main.
