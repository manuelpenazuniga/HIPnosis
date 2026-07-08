ENTORNO: para verificar usá el intérprete del venv compartido (ya tiene pydantic, gitpython, pytest):
  /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python
Ejemplo: cd orchestrator && /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python -m pytest tests/ -q   |   /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python -c "from core.schemas import Run; print('ok')"
NO crees otro venv ni instales deps. NO uses 'python' pelado (el sistema no tiene las libs).

Trabajás en el worktree actual (rama spike/t4-gitrepo). Implementá SOLO esta tarea.

--- TAREA T4: core/gitrepo.py — wrapper de gitpython para el workspace del repo OBJETIVO ---
Un módulo que envuelve operaciones git sobre el repositorio que el pipeline está portando
(NO sobre el repo de HIPnosis). Es una PRIMITIVA PURA (capa L2): importa solo de schemas/config
y de gitpython. NO importa phases, oracle, llm, state.

ARCHIVO A TOCAR (solo este de producto): orchestrator/core/gitrepo.py
+ un test: orchestrator/tests/test_gitrepo.py

### Contrato de gitrepo.py — clase `GitRepo` que envuelve un directorio de trabajo:

    class GitRepo:
        def __init__(self, path: str): ...        # path al workspace ya existente o a clonar

        @classmethod
        def clone(cls, url: str, dest: str) -> "GitRepo": ...
            # git clone url dest (shallow: depth=1 está OK). Devuelve GitRepo(dest).

        def checkout_branch(self, name: str) -> None: ...
            # crea y cambia a una rama nueva (git checkout -b name). Si ya existe, cambia a ella.

        def commit_all(self, message: str) -> str: ...
            # git add -A && git commit -m message. Devuelve el sha corto del commit.
            # Si no hay cambios que commitear, devolvé "" (no explotes).

        def revert_head(self) -> None: ...
            # revierte el ÚLTIMO commit dejando el árbol como antes de ese commit.
            # Usá `git reset --hard HEAD~1` (el workspace es efímero por run; no hace falta
            # preservar historial de un fix descartado). Documentá esa decisión en un docstring.

        def head_sha(self) -> str: ...            # sha corto de HEAD

        def current_branch(self) -> str: ...

        def is_dirty(self) -> bool: ...           # ¿hay cambios sin commitear?

Usá `git` de gitpython (`from git import Repo`). Todas las operaciones sobre el path del
workspace. Manejá el caso de repo sin commits previos donde tenga sentido. Configurá
user.name/user.email localmente en el repo si hace falta para poder commitear (usá algo como
"HIPnosis Pipeline" / "pipeline@hipnosis.local"); esto es un commit del WORKSPACE OBJETIVO,
legítimo (los hace el pipeline).

### Test test_gitrepo.py (pytest, con fixtures reales — tmp_path):
- test_clone_o_init + checkout_branch: creá un repo git temporal local (o init en tmp_path con
  un archivo y un commit inicial), abrilo con GitRepo, creá una rama, verificá current_branch.
- test_commit_all_devuelve_sha: modificá un archivo, commit_all, verificá que head_sha cambió y
  que commit_all sobre árbol limpio devuelve "".
- test_revert_head: hacé un commit, revert_head, verificá que el archivo volvió al estado previo
  y que head_sha es el anterior.
- test_is_dirty: verificá True con cambios sin commitear, False tras commit.
NO uses red en los tests (nada de clone real de internet): construí repos locales en tmp_path.

--- FIN TAREA ---

Criterios de aceptación:
1. `python -m pytest tests/test_gitrepo.py -q` desde orchestrator/ pasa en verde (todos los tests).
2. gitrepo.py importa solo de gitpython (y opcionalmente schemas/config). NO importa phases/oracle/llm/state (test negativo: un grep de esos nombres en el archivo da vacío).
3. revert_head deja el árbol EXACTAMENTE como antes del commit revertido (test lo verifica).

Reglas duras:
- INV-3: todo cambio al repo objetivo pasa por acá como commit atómico; este módulo es la única puerta de escritura git del pipeline. Diseñá las firmas para que sea imposible reescribir un archivo completo sin pasar por un commit.
- Capa L2: NO importar hacia arriba (phases/oracle/llm/state). Primitiva pura.
- NO inventes APIs de gitpython: si dudás de un método, abrí la doc mental de gitpython real (Repo.index, Repo.git.checkout, etc.) o usá `repo.git.<comando>(...)` que ejecuta git crudo.
- NO agregues dependencias nuevas (gitpython ya está en pyproject). NO toques otros archivos.
- Al terminar: corré el pytest, dejalo verde, y HACÉ COMMIT (`git add -A && git commit -m "feat(core): gitrepo wrapper + tests"`).
- Respuesta final CORTA: qué creaste + output literal del pytest. Sin ensayos.
- Si te bloqueás: 'BLOCKED | ENV|SPEC|DEPS: <motivo>' y pará.