#!/usr/bin/env bash
# record_demo_cast.sh — graba un asciinema cast REAL del pipeline y lo deja
# listo para el README/video. Complementa a record_fixture.sh: ese congela el
# TRACE (lo que ve el dashboard en replay); éste congela la TERMINAL (el
# POST /runs → eventos drenando → PASS), que es la evidencia que un juez
# reproduce sin GPU.
#
# La diferencia con la competencia: acá NADA está hardcodeado. El cast captura
# la salida real de la API; si el run no llega a PASS, el cast lo muestra. No
# hay `echo ">>> PASSED <<<"` inventado (ese fue el error de un rival — texto
# literal en un script de demo, con warpSize=32 en una MI300X wave64).
#
# Uso:
#   # En el droplet (run REAL en MI300X, oracle_mode=real) — lo ideal:
#   scripts/record_demo_cast.sh https://github.com/<...>/bsw-cuda
#   # O contra un stack local en replay/mock para un cast de la UX de la API:
#   scripts/record_demo_cast.sh --repo bsw --base http://localhost:8080
#
# Produce:
#   assets/demo.cast   — asciinema v2 (reproducible con `asciinema play`)
#   assets/demo.gif    — si `agg` está instalado (asciinema gif generator)
#
# Requisitos: asciinema (`pip install asciinema` o el paquete del SO), curl, jq.
# Opcional: agg (https://github.com/asciinema/agg) para el GIF.
set -euo pipefail

BASE="http://localhost:8080"
REPO_URL=""
POLL_MAX="${POLL_MAX:-180}"   # s máximos esperando a que el run termine

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    http*) REPO_URL="$1"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "arg desconocido: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$REPO_URL" ]]; then
  echo "uso: $0 <repo_url|--repo <key>> [--base <url>]" >&2
  exit 2
fi

for bin in asciinema curl jq; do
  command -v "$bin" >/dev/null 2>&1 || { echo "ERROR: falta '$bin' en el PATH" >&2; exit 1; }
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$REPO_ROOT/assets"
mkdir -p "$ASSETS"
CAST="$ASSETS/demo.cast"
GIF="$ASSETS/demo.gif"

# El "guion" que graba asciinema es este script interno: dispara el run por API
# y poléa /runs/<id> hasta un estado final, imprimiendo cada transición. Todo lo
# que se ve en el cast sale de la API — cero texto inventado.
INNER="$(mktemp)"
trap 'rm -f "$INNER"' EXIT
cat > "$INNER" <<INNERSCRIPT
#!/usr/bin/env bash
set -euo pipefail
BASE="$BASE"; REPO_URL="$REPO_URL"; POLL_MAX="$POLL_MAX"
echo "\$ curl -X POST \$BASE/runs -d '{\"repo_url\":\"\$REPO_URL\"}'"
RID=\$(curl -fsS -X POST "\$BASE/runs" -H 'Content-Type: application/json' \\
       -d "{\"repo_url\":\"\$REPO_URL\"}" | jq -r '.id')
echo "  run: \$RID"
echo
prev=""
for i in \$(seq 1 "\$POLL_MAX"); do
  run=\$(curl -fsS "\$BASE/runs/\$RID")
  state=\$(echo "\$run" | jq -r '.state')
  ei=\$(echo "\$run" | jq -r '.counters.errors_initial // 0')
  ec=\$(echo "\$run" | jq -r '.counters.errors_current // 0')
  line="[\$state] errors: \$ec/\$ei"
  if [[ "\$line" != "\$prev" ]]; then echo "  \$line"; prev="\$line"; fi
  case "\$state" in
    DONE|DONE_PARTIAL|FAILED)
      echo
      echo "  final: \$state"
      echo "\$run" | jq '{verdict: .verify_result.verdict, counters: .counters}' 2>/dev/null || true
      exit 0 ;;
  esac
  sleep 1
done
echo "  timeout esperando estado final (\$POLL_MAX s)"; exit 1
INNERSCRIPT
chmod +x "$INNER"

echo "Grabando cast del run REAL contra $BASE …"
asciinema rec --overwrite --command "$INNER" "$CAST"
echo "✓ cast -> assets/demo.cast"

if command -v agg >/dev/null 2>&1; then
  agg "$CAST" "$GIF"
  echo "✓ gif  -> assets/demo.gif"
else
  echo "ℹ️  'agg' no instalado — sin GIF. Instalá: cargo install --git https://github.com/asciinema/agg"
  echo "   (o subí el .cast a asciinema.org y enlazá el player en el README)"
fi

echo
echo "Siguiente (desde tu Mac, no en el droplet efímero):"
echo "  scp root@<ip>:HIPnosis/assets/demo.cast assets/  # y demo.gif si existe"
echo "  git add assets/demo.cast assets/demo.gif && git commit -m 'chore(assets): cast real del run en MI300X'"
