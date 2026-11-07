#!/usr/bin/env bash
# Cifra a vinheta com uma senha aleatória e grava a senha no secret VINHETA_SENHA do repositório.
# A senha não é exibida nem salva em disco: para trocar a vinheta, basta rodar o script de novo.
#
#   scripts/cifrar_vinheta.sh [assets/vinheta.mp3]
set -euo pipefail

origem="${1:-assets/vinheta.mp3}"
repo="${REPO:-lucas-jdev/pebacast}"
destino="assets/vinheta.mp3.gpg"

[ -f "$origem" ] || { echo "Não encontrei $origem." >&2; exit 1; }
mkdir -p assets
[ "$origem" -ef assets/vinheta.mp3 ] || cp "$origem" assets/vinheta.mp3

senha="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
gpg_senha() { gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 "$@"; }

printf '%s' "$senha" | gpg_senha --symmetric --cipher-algo AES256 -o "$destino" assets/vinheta.mp3
printf '%s' "$senha" | gpg_senha -d "$destino" | cmp -s - assets/vinheta.mp3 \
  || { echo "A conferência da cifra falhou; nada foi alterado no GitHub." >&2; exit 1; }
printf '%s' "$senha" | gh secret set VINHETA_SENHA --repo "$repo"

echo "Pronto: $destino cifrado e secret VINHETA_SENHA atualizado em $repo."
echo "Commite só o $destino; o .gitignore impede que o MP3 original entre no repositório."
