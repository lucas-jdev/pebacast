#!/usr/bin/env bash
# Avisa quando a rotina do roteirista para de commitar (ADR 0006).
# Escreve "parada" ou "ok" na primeira linha e, se parada, o corpo da issue em seguida.
#
#   scripts/watchdog.sh [limite_em_horas]     (AGORA=<epoch> sobrescreve o relógio, para testes)
set -euo pipefail

limite_horas="${1:-36}"
agora="${AGORA:-$(date +%s)}"
ultimo="$(git log -1 --format=%ct -- 'episodios/*/roteiro.json' 'episodios/*/revisoes' || true)"

if [ -z "$ultimo" ]; then
  echo parada
  echo "Nenhum roteiro foi commitado em \`episodios/\` até agora."
  exit 0
fi

horas=$(( (agora - ultimo) / 3600 ))
if [ "$horas" -le "$limite_horas" ]; then
  echo ok
  exit 0
fi

quando="$(date -u -d "@$ultimo" '+%Y-%m-%d %H:%M UTC' 2>/dev/null || echo "$ultimo")"
echo parada
cat <<CORPO
A rotina do roteirista não commita um roteiro em \`episodios/\` há ${horas} horas (limite: ${limite_horas}).
Último commit de roteiro: ${quando}.

Causas prováveis:
- a rotina não rodou ou quebrou (ver as execuções em https://claude.ai/code/routines);
- não há episódio disponível: referências não verificadas no currículo, ou um roteiro aprovado esperando publicação;
- o push da rotina foi recusado.

Esta issue fecha sozinha quando um novo roteiro for commitado.
CORPO
