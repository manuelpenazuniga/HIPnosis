Sos un auditor adversarial. Objetivo: encontrar un caso donde core/patcher.py haga una EDICIÓN
SILENCIOSA ERRÓNEA o corrompa el repo objetivo. NO ejecutes nada (read-only): razoná sobre el código.

Contexto: patcher aplica bloques SEARCH/REPLACE al repo que se está portando CUDA→HIP. Es F-05:
un bug acá corrompe silenciosamente y gatea CADA fix del loop. Invariantes duros:
- INV-3: SEARCH debe matchear EXACTAMENTE 1 vez; 0→NOT_FOUND, >1→AMBIGUOUS; JAMÁS aplicar en
  ambigüedad; jamás fuzzy; all-or-nothing (si un bloque falla, NINGÚN archivo se escribe).
- INV-4: evento al trace ANTES de escribir.
- Post-write self-check: el REPLACE debe quedar presente; si no, revert (gitrepo reset HEAD~1).

Archivos a auditar (leelos): orchestrator/core/patcher.py y orchestrator/tests/test_patcher.py
(en /Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t11/).

Buscá ADVERSARIALMENTE (dame un input concreto que rompa, si existe):
1. ¿Puede escribirse un archivo cuando algún bloque debía fallar? (violación all-or-nothing)
2. Multi-bloque en el MISMO archivo: el reemplazo se hace en orden inverso de posición y RE-BUSCA
   search en el contenido ya modificado. ¿Hay un caso donde el REPLACE de un bloque contenga el
   SEARCH de otro y el índice [0] apunte a la ocurrencia equivocada? ¿O donde la unicidad validada
   sobre el contenido original ya no valga tras modificar?
3. Normalización CRLF→LF: ¿puede desalinear posiciones o corromper un archivo con contenido mixto?
4. El self-check `blk.replace not in content_after`: ¿falso-positivo si el REPLACE ya existía en otra
   parte del archivo? ¿Deja pasar un REPLACE que NO se aplicó realmente?
5. _is_path_safe / _is_binary_or_missing: ¿algún path malicioso (symlink, `..` codificado, absoluto)
   que escape del workspace y NO sea rechazado?
6. ¿Alguna excepción no capturada (permisos, archivo borrado entre check y write) que deje el repo
   en estado inconsistente (escrito sin commit, o commit sin revert)?

Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`. Por hallazgo: severidad + patcher.py:línea
+ el INPUT CONCRETO que lo dispara + fix en una frase. ÚLTIMA línea `END_AUDIT`.
