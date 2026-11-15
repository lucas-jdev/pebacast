#!/usr/bin/env bash
# Gera os prints do site para PRs que mudam o visual: página inicial e de episódios, no desktop e no celular.
# Rode uma vez no main (antes) e outra no branch do PR (depois), com pastas de saída diferentes.
#
#   scripts/prints.sh <pasta_de_saida>     (PYTHON=<interpretador> e PORTA=<porta> são opcionais)
set -euo pipefail

saida="${1:?informe a pasta de saída}"
python="${PYTHON:-.venv/bin/python}"
porta="${PORTA:-8765}"
chrome="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
[ -n "$chrome" ] || { echo "Chrome ou Chromium não encontrado no PATH." >&2; exit 1; }

site="$(mktemp -d)"
trap 'kill "${servidor:-}" 2>/dev/null || true; rm -rf "$site"' EXIT

"$python" -m podcast.publicacao --site "$site" feed >/dev/null
mkdir -p "$saida"
python3 -m http.server "$porta" --directory "$site" >/dev/null 2>&1 &
servidor=$!
sleep 1

for pagina in index episodios; do
  for tela in desktop:1280,3200 celular:390,4200; do
    "$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
      --window-size="${tela#*:}" --screenshot="$saida/$pagina-${tela%%:*}.png" \
      "http://localhost:$porta/$pagina.html" 2>/dev/null
  done
done

ls "$saida"
