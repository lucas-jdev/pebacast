#!/usr/bin/env bash
# Gera site/capa.jpg (3000x3000, RGB) a partir de assets/capa.svg.
# Precisa do Chrome (ou de outro Chromium em $CHROME) e do ffmpeg. As fontes vêm do Google Fonts.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
chrome="${CHROME:-chrome}"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
# No Git Bash do Windows o Chrome precisa de caminhos C:/...
caminho() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else echo "$1"; fi; }

"$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=3000,3000 --virtual-time-budget=8000 \
  --screenshot="$(caminho "$temp/capa.png")" "file:///$(caminho "$raiz/assets/capa.svg")" 2>/dev/null

ffmpeg -loglevel error -y -i "$temp/capa.png" -pix_fmt yuvj444p -q:v 3 "$raiz/site/capa.jpg"
echo "site/capa.jpg: $(wc -c < "$raiz/site/capa.jpg") bytes"
