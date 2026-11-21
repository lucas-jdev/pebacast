# 0011. Cota diária esgotada espera a renovação em vez de cair no Kokoro

- Status: Aceito
- Data: 2026-11-20
- Revisa: [ADR 0001](0001-tts-gemini-com-fallback-kokoro.md), só para a cota diária esgotada

## Contexto

O ADR 0001 manda o episódio para o Kokoro sempre que o Gemini falha. No free tier, o `gemini-3.8-flash-tts` aceita 10 requisições por dia, e um episódio usa de 4 a 5. Uma regravação no mesmo dia, ou uma série de tentativas, basta para esgotar a cota.

No Kokoro, as personas dividem vozes (`pf_dora`, `pm_santa`) e o episódio sai sem emoção. Corrigir depois exige regravar e substituir (ADR 0008), e quem baixou o episódio no dia fica com a versão ruim.

A cota diária é a única falha do Gemini com hora certa para acabar: ela renova à meia-noite do horário do Pacífico, 07:00 ou 08:00 UTC conforme o horário de verão de lá.

## Decisão

Enquanto o pebacast estiver em beta e no free tier, um episódio que encontra a cota diária esgotada (`CotaDiariaEsgotada`) **não é publicado e não vai para o Kokoro**:

- a pipeline grava `episodios/<id>/aguardando_cota.json` e abre a issue `incidente` "Cota do Gemini esgotada: &lt;id&gt; aguardando";
- o card "Próximo" do site avisa que houve um problema interno e que o episódio sai em breve, sem prometer hora;
- o `publicar.yml` ganha um agendamento às 08:15 UTC, depois da renovação em qualquer época do ano, que só passa da verificação se houver episódio **aguardando a cota** (pasta com `aguardando_cota.json` e sem `publicacao.json`). Um roteiro reprovado parado na pasta não conta, senão ganharia o mesmo comentário na issue todo dia (#77);
- ao publicar, o arquivo é apagado e a issue fecha.

As outras falhas do principal (401/403, indisponibilidade depois das tentativas) continuam indo para o Kokoro, como no ADR 0001.

Decisão do Lucas, na lapidação da #36 (20/11). Contraria, só neste caso, a regra do épico #18 de que o ritmo diário pesa mais: uma voz ruim dura para sempre no feed, e um dia de atraso some no dia seguinte.

## Consequências

Positivas:

- Nenhum episódio vai ao ar no Kokoro só por falta de cota.
- O ouvinte que abre o site vê por que o episódio não saiu, em vez de uma página parada.
- Quando o episódio sai, nada precisa ser regravado.

Negativas:

- A fila anda um dia. Com um roteiro aprovado sem publicar, a rotina não escreve outro ("Nada a escrever hoje").
- Se a cota continuar esgotada às 08:15, o episódio segue aguardando sem limite de dias. A issue aberta é o alarme.
- Um run diário a mais no Actions, que termina em segundos quando não há episódio aguardando a cota.

## Quando revisar

Ao sair do free tier, ou ao lançar no Spotify para outras pessoas: com plano pago, a cota diária deixa de ser o gargalo, e esta exceção perde o motivo.
