#!/usr/bin/env bash
# record_fixture.sh — congela un run REAL como los fixtures del modo replay.
#
# Cierra el problema de procedencia del audit (P0.2 / Gate D): en vez de editar
# a mano el trace del demo, este script toma un run que YA corrió (idealmente en
# la MI300X, oracle_mode=real) y copia su trace + diff + certificado a fixtures/,
# de modo que `docker compose --profile replay up` reproduzca esa corrida real.
#
# Uso (en el droplet, DESPUÉS de que un run llegue a DONE):
#   scripts/record_fixture.sh <run_id>
#
# El run_id sale del dashboard o de: curl -s localhost:8080/runs | jq -r '.[].id'
set -euo pipefail

RUN_ID="${1:-}"
if [[ -z "$RUN_ID" ]]; then
  echo "uso: $0 <run_id>" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="$REPO_ROOT/orchestrator/workspaces/$RUN_ID"
TRACE="$WS/trace.jsonl"
REPO_DIR="$WS/repo"
FIXTURES="$REPO_ROOT/fixtures"

if [[ ! -f "$TRACE" ]]; then
  echo "ERROR: no existe el trace $TRACE" >&2
  echo "  ¿el run_id es correcto y corrió en ESTA máquina?" >&2
  exit 1
fi

# --- Procedencia: verificar que fue un run REAL, no mock -------------------
mode="$(grep -o '"oracle_mode":"[a-z]*"' "$TRACE" | head -1 | cut -d'"' -f4 || true)"
verdict="$(grep -o '"verdict":"[A-Z_]*"' "$TRACE" | tail -1 | cut -d'"' -f4 || true)"
echo "run_id     : $RUN_ID"
echo "oracle_mode: ${mode:-<none>}"
echo "verdict    : ${verdict:-<none>}"

if [[ "$mode" != "real" ]]; then
  echo
  echo "⚠️  Este trace NO es oracle_mode=real (es '${mode:-none}')."
  echo "   El punto del script es reemplazar el demo SINTÉTICO por una corrida REAL."
  read -r -p "   ¿Grabar igual? (solo si sabés lo que hacés) [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "abortado."; exit 1; }
fi

# --- Copiar los 3 artefactos ----------------------------------------------
cp "$TRACE" "$FIXTURES/demo-run.jsonl"
echo "✓ trace  -> fixtures/demo-run.jsonl"

CERT="$REPO_DIR/HIPNOSIS_CERTIFICATE.md"
if [[ -f "$CERT" ]]; then
  cp "$CERT" "$FIXTURES/demo-certificate.md"
  echo "✓ cert   -> fixtures/demo-certificate.md"
else
  echo "⚠️  sin certificado en $CERT (¿run DONE_PARTIAL/FAILED?)"
fi

# diff root..HEAD del workspace porteado (la transformación CUDA→HIP real)
if [[ -d "$REPO_DIR/.git" ]]; then
  base="$(git -C "$REPO_DIR" rev-list --max-parents=0 HEAD | head -1)"
  git -C "$REPO_DIR" diff "$base" HEAD > "$FIXTURES/demo-diff.txt"
  echo "✓ diff   -> fixtures/demo-diff.txt"
fi

echo
echo "Listo. El modo replay ahora reproduce el run REAL $RUN_ID."
echo "El badge del dashboard pasará de 'synthetic demo' a 'recorded run'"
echo "automáticamente (deriva oracle_mode del propio trace)."
echo
echo "Siguiente:"
echo "  git add fixtures/demo-run.jsonl fixtures/demo-certificate.md fixtures/demo-diff.txt"
echo "  git commit -m 'chore(fixtures): trace real de M0 ($RUN_ID) reemplaza el sintetico'"
echo "  git push"
