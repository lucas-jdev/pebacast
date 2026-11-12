#!/usr/bin/env bash
# Gera as imagens publicadas do site a partir das artes em assets/:
#   site/capa.jpg (3000x3000), capa do podcast no feed, de assets/capa.svg
#   site/og.jpg (1200x630), prévia de compartilhamento (Open Graph), de assets/og.svg
# Precisa do Chrome (ou de outro Chromium em $CHROME) e do ffmpeg.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
chrome="${CHROME:-chrome}"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
# No Git Bash do Windows o Chrome precisa de caminhos C:/...
caminho() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else echo "$1"; fi; }

renderizar() {
  local arte="$1" largura="$2" altura="$3" destino="$4"
  "$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --allow-file-access-from-files --window-size="$largura,$altura" --virtual-time-budget=8000 \
    --screenshot="$(caminho "$temp/imagem.png")" "file:///$(caminho "$raiz/assets/$arte")" 2>/dev/null
  ffmpeg -loglevel error -y -i "$temp/imagem.png" -pix_fmt yuvj444p -q:v 3 "$raiz/site/$destino"
  echo "site/$destino: $(wc -c < "$raiz/site/$destino") bytes"
}

renderizar capa.svg 3000 3000 capa.jpg
renderizar og.svg 1200 630 og.jpg
