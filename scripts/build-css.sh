#!/usr/bin/env bash
# Regenera dashboard/vendor/tailwind.css a partir de las clases usadas en
# index.html + app.js. Correr SOLO cuando cambien clases del dashboard; el
# output se commitea (no hay build step en runtime — F-15).
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
printf '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n' > /tmp/hipnosis-tw-input.css
npx --yes tailwindcss@3.4.17 -c tailwind.config.js -i /tmp/hipnosis-tw-input.css -o vendor/tailwind.css --minify
echo "OK -> dashboard/vendor/tailwind.css"
