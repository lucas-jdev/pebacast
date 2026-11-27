# 0008. Regravação do áudio em dois passos, sem mudar o episódio no feed

- Status: Aceito
- Data: 2026-11-14

## Contexto

O Gemini TTS não é determinístico: o mesmo roteiro pode sair com vozes trocadas, timbre que muda entre blocos ou pausas estranhas. Em 2026-11-14 o sw-002 foi regravado à mão, com um workflow avulso num branch temporário, e a nova versão ficou bem melhor. O Lucas quer repetir isso quando um áudio sair ruim, sem refazer o roteiro e sem que o episódio reapareça como novo para quem assina o feed.

O ADR 0002 já fixa que o GUID nunca muda, mesmo com o áudio regenerado. Faltava o caminho para regenerar.

## Decisão

A regravação é um workflow manual (`regravar.yml`) com dois passos, porque só um humano julga se o áudio novo ficou melhor:

1. **regravar**: valida o roteiro de novo, narra com o TTS principal e anexa `pebacast-<id>-candidata.mp3` ao release do episódio. O feed e o `publicacao.json` não mudam.
2. **substituir**: depois de ouvir, troca `pebacast-<id>.mp3` pela candidata, remove a candidata e atualiza no `publicacao.json` o tamanho, a duração, o TTS e o novo campo `regravado_em`. URL, GUID e `publicado_em` continuam os mesmos, então o episódio não volta ao topo da lista nos apps.

Regras:

- **Sem fallback.** Se o Gemini falhar, a regravação falha. Uma candidata no Kokoro seria pior que o áudio no ar.
- **Sem vinheta, sem regravação.** Se a vinheta está configurada e não foi decifrada, falha, para o áudio não piorar e o crédito no feed continuar correto.
- **Só episódio publicado.** A primeira narração continua sendo da publicação.
- **Uma candidata por vez.** Regravar de novo sobrescreve a candidata anterior.
- O workflow usa o mesmo grupo de concorrência da publicação, porque os dois mexem no release, no `publicacao.json` e no Pages.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| Regravar e substituir num passo só | Mais simples | Ninguém ouve antes de ir ao ar, e o sorteio do TTS pode sair pior |
| Republicar como episódio novo (GUID novo) | Ouvintes recebem aviso | Duplica o episódio no app e quebra a regra 2 do ADR 0002 |
| Regravar automaticamente quando o QA de áudio reprovar | Sem trabalho manual | O QA de áudio ainda não existe; quando existir, ele pode disparar o passo 1 |

## Consequências

Positivas:

- Corrigir um áudio ruim vira dois cliques no Actions, sem branch nem código avulso.
- O histórico do `publicacao.json` mostra quando e com qual TTS o áudio foi trocado.

Negativas:

- O `gh release upload --clobber` apaga o asset antigo antes de subir o novo. Por alguns segundos a URL do episódio dá 404. Se o upload falhar no meio, a candidata continua no release, e rodar **substituir** de novo resolve.
- Quem já baixou o episódio no app fica com o áudio antigo até baixar de novo.
- Regravar não corrige a causa. Problema recorrente de voz se resolve na pipeline, não sorteando o TTS de novo.

## Nota (2026-11-27)

O QA de voz pode disparar o passo 1 sozinho, no modo `regravar` ([ADR 0012](0012-qa-de-voz.md)): só a publicação dispara, no máximo uma candidata automática por episódio, e o passo 2 continua manual. Este ADR segue valendo como está.
