#!/usr/bin/env bash
# Gera os prints do site, um por seção (cabeçalho, cada <section> e rodapé) de index.html e episodios.html,
# no desktop (1280 px) e no celular (390 px). Usa o Playwright via scripts/prints.py (ADR 0009).
# Nos PRs, os workflows Capturar e Comentar fazem isso sozinhos; este script é para olhar localmente.
#
#   scripts/prints.sh <pasta_de_saida>     (PYTHON=<interpretador> é opcional)
#
# Precisa do extra "prints": pip install -e ".[prints]" && python -m playwright install chromium
# Para comparar, rode no main e no branch com pastas diferentes e depois:
#   python scripts/prints.py comparar <pasta_main> <pasta_branch> --saida <pasta_diferencas>
set -euo pipefail

saida="${1:?informe a pasta de saída}"
python="${PYTHON:-.venv/bin/python}"
raiz="$(cd "$(dirname "$0")/.." && pwd)"

"$python" -c "import playwright, PIL" 2>/dev/null || {
  echo "Playwright ou Pillow ausente: $python -m pip install -e \".[prints]\" && $python -m playwright install chromium" >&2
  exit 1
}

site="$(mktemp -d)"
trap 'rm -rf "$site"' EXIT

"$python" -m podcast.publicacao --raiz "$raiz" --site "$site" feed >/dev/null
"$python" "$raiz/scripts/prints.py" capturar --site "$site" --saida "$saida" >/dev/null
ls "$saida"
