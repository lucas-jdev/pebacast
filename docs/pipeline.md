# Pipeline de geração

Roda uma vez por dia, na noite anterior ao episódio. Cada etapa grava sua saída em `episodios/<id>/`, o que deixa a geração auditável: dá para ver de onde veio cada fala e o que o revisor corrigiu.

A pipeline tem duas partes, ligadas por um commit ([ADR 0006](adr/0006-roteiro-por-rotina-claude.md)):

```
Rotina do Claude (rotina/roteirista.md)                     GitHub Actions
seleção → notícias → roteiro → revisão ⇄ correção  ──push──▶  validar → voz → montagem → publicação → QA do áudio
```

Arquivos de cada episódio:

| Arquivo | Quem grava | Conteúdo |
|---|---|---|
| `noticia.json` | rotina | notícia usada ou cenário hipotético |
| `roteiro.json` | rotina | diálogo final |
| `revisoes/1.json`, `2.json`, ... | subagente revisor | relatório de cada revisão |
| `publicacao.json` | Actions | GUID, URL do MP3 e data. Marca o episódio como publicado. `regravado_em` aparece se o áudio foi regravado |

## 1. Seleção do episódio

`python -m podcast.roteiro contexto` escolhe, na ordem do currículo, o próximo episódio não publicado cujos pré-requisitos já foram publicados e cujas referências estão verificadas. Se algum episódio já tem roteiro aprovado e ainda não foi publicado, nada novo é escrito.

As sagas consideradas dependem de `agenda.modo` em `config/pipeline.yaml`:

| Modo | Sagas consideradas |
|---|---|
| `fila` | Todas as da lista `agenda.fila`. Primeiro as que nunca foram publicadas, depois a publicada há mais tempo; empates seguem a ordem da lista. Verificar as referências de um episódio basta para ele entrar na produção. |
| `saga_unica` | Só `agenda.saga_unica`. |
| `rotacao_semanal` | Só a saga do dia da semana da publicação. |

Saída: o spec do episódio, as referências, as personas envolvidas, as regras e os feedbacks recentes da saga.

## 2. Contexto de notícias

Busca uma notícia que ilustre o problema do episódio, ampliando a janela em cascata:

| Tentativa | Janela |
|---|---|
| 1 | últimos 7 dias |
| 2 | últimos 30 dias |
| 3 | últimos 60 dias |
| 4 | nenhuma notícia: cenário hipotético |

**Critério de relevância.** Um juiz avalia cada notícia candidata com nota de 0 a 10 e uma justificativa ligando a notícia a pelo menos um objetivo do episódio. Só passa com nota mínima definida em `config/pipeline.yaml`. Sem esse limiar, o modelo tende a forçar uma conexão com qualquer notícia.

**Notícias já usadas.** As notícias dos episódios publicados (`episodios/*/noticia.json`) não podem ser repetidas.

**Cenário hipotético.** É apresentado explicitamente como hipotético no áudio ("imagine uma empresa que...").

Saída: `noticia.json`, com a notícia e sua fonte, ou o cenário marcado como hipotético.

## 3. Roteiro

O roteirista recebe o spec, as personas, o contexto de notícias e os feedbacks recentes e devolve o diálogo em JSON. O campo `estilo` de cada fala é opcional e vai para o TTS somado à instrução de voz da persona, sem substituí-la: o Gemini recebe a instrução da persona, depois `Nesta fala: <estilo>.` e, por fim, as instruções do dicionário de pronúncia, cada uma uma vez só (`Fala.estilo_efetivo`):

```json
{
  "episodio": "sw-001",
  "falas": [
    { "persona": "davi", "texto": "..." },
    { "persona": "helena", "texto": "..." }
  ],
  "desafio": "...",
  "fontes": ["fosa cap. 1", "fosa cap. 2"]
}
```

Estrutura fixa do episódio: abertura com boas-vindas ao Pebacast e aviso de conteúdo gerado por IA, apresentação do expert convidado, problema ou notícia, solução ingênua do apresentador, desconstrução pelo expert, trade-offs, resumo, desafio e despedida. O `validar` confere a abertura: a primeira fala cita o Pebacast e traz o aviso de IA, e nas três primeiras falas o apresentador diz o nome do expert e o expert fala.

## 4. Revisão

O revisor é um subagente novo a cada revisão, sem o contexto do roteirista, e segue `rotina/revisor.md`. Ele não reescreve o roteiro:

1. Extrai do roteiro cada afirmação verificável.
2. Checa cada afirmação contra as referências do spec e, quando necessário, por busca.
3. Devolve um relatório com veredito por afirmação.

```json
{
  "aprovado": false,
  "afirmacoes": [
    {
      "fala": 12,
      "afirmacao": "...",
      "veredito": "incorreta",
      "correcao": "...",
      "fonte": "..."
    }
  ]
}
```

Vereditos possíveis: `correta`, `incorreta`, `imprecisa` e `nao_verificavel`. O roteiro é aprovado quando não há `incorreta` nem `imprecisa`. O relatório também traz `roteiro_sha256`, o hash do roteiro revisado (`python -m podcast.roteiro hash <id>`). Os motivos dessa separação estão em [ADR 0004](adr/0004-roteiro-com-revisor-independente.md).

## 5. Correção

O roteirista recebe o relatório e corrige só as falas apontadas. Revisão e correção se repetem por no máximo dois ciclos, mais uma revisão final, o que dá até 3 revisões.

A rotina commita a pasta do episódio, aprovada ou não. O Actions roda `python -m podcast.roteiro validar <id>`. Se reprovar, a pipeline falha fechada: não publica e abre uma issue com os problemas. É melhor perder um dia do que publicar um conceito errado.

## 6. Voz

Roda no GitHub Actions (`.github/workflows/publicar.yml`), com `python -m podcast.publicacao publicar`, só depois de o `validar` aprovar o roteiro de novo.

Cada fala é sintetizada pelo `TtsProvider` configurado, com no máximo dois falantes por requisição. O silêncio que o TTS deixa nas bordas de cada bloco é aparado (abaixo de −50 dBFS, com 30 ms de folga) antes de os blocos serem emendados com a pausa fixa de 300 ms; sem isso, a troca de bloco chegava a 1,1 s de silêncio. A montagem guarda onde fica cada troca, para o QA medir. Cada bloco do Gemini tem até 4 tentativas, com espera exponencial a partir de 15 s, porque o free tier devolve 429 com frequência. Se o provedor principal ainda assim falhar, a pipeline usa o fallback e abre uma issue avisando. A decisão está em [ADR 0001](adr/0001-tts-gemini-com-fallback-kokoro.md).

## 7. Montagem

O ffmpeg mistura a fala com a vinheta e exporta em MP3 mono a 64 kbps, com cerca de 10 MB por episódio. Com a vinheta configurada, o recorte toca na abertura, por baixo da primeira fala, e no encerramento ([docs/vinheta.md](vinheta.md)).

- **Música nivelada pela fala.** A loudness de cada recorte da vinheta é medida e ajustada para ficar `audio.vinheta.abaixo_da_fala_lu` (2 LU) abaixo da loudness da fala do episódio, seja qual for o volume da faixa.
- **Ganho único até −16 LUFS.** O episódio inteiro recebe um só ganho, calculado pela loudness medida. O loudnorm, usado antes, é dinâmico: puxava a música do encerramento, mais baixa que a fala, para o alvo.
- **Pico real limitado.** Depois do ganho, um limitador com a taxa quadruplicada (para enxergar o pico entre amostras) segura o pico real em −1,5 dBTP. O codificador MP3 ainda sobe o pico e tira alguns décimos de LU, então a montagem mede o MP3 e, se precisar, codifica de novo com o teto mais baixo e o ganho corrigido (até 3 passadas).

## 8. Publicação

O MP3 vai para o `AudioStorage` (um release `episodio-<id>` por episódio) e o Actions commita `publicacao.json`. O `feed.xml` é regenerado inteiro a partir de `episodios/` e publicado no GitHub Pages, em https://lucas-jdev.github.io/pebacast/feed.xml. Ele traz:

- GUID imutável do episódio;
- show notes com as fontes, o desafio e o resumo do relatório de revisão;
- aviso de conteúdo gerado por IA.

Mudanças que só afetam o site ou o feed (`site/`, `src/podcast/site.py`, `src/podcast/publicacao.py`, `curriculum/`, `config/`) são publicadas por `.github/workflows/site.yml`, sem esperar episódio novo. Ele também pode ser disparado à mão. Ele faz checkout da ponta do `main`, e não do commit que o disparou: se ficou na fila esperando uma publicação de episódio, ele publica o `main` já com o episódio novo. Pelo mesmo motivo, `publicar.yml` e `regravar.yml` geram o site de novo depois do `git pull --rebase`, antes do deploy.

O site ganha uma página por episódio publicado em `episodios/<id>/`, e o `<link>` de cada item do feed aponta para ela. Essa URL não muda, e o id do episódio não é renomeado depois de publicado ([ADR 0010](adr/0010-url-permanente-do-episodio.md)).

Decisão de hospedagem em [ADR 0002](adr/0002-hospedagem-pages-releases.md).

### Entrar no índice dos buscadores

As IAs que respondem com busca na web só acham o que está no índice do Google (Gemini, AI Overviews) ou do Bing (ChatGPT, Copilot). O site mora numa subpasta do `github.io`, então não dá para pôr arquivo de verificação nem `robots.txt` na raiz do domínio. Por isso, a verificação vai por meta tag e o IndexNow usa uma chave publicada dentro da subpasta.

Depois de cada deploy, `publicar.yml` e `site.yml` rodam `python -m podcast.indexacao --site _site avisar`. O comando manda ao IndexNow as URLs do `sitemap.xml` com `lastmod` nos últimos 2 dias. Sem chave configurada, não faz nada. Resposta de erro ou falha de rede viram um `::warning::` no log, e a publicação segue.

Configuração, feita uma vez pelo Lucas:

1. **Search Console.** Em [search.google.com/search-console](https://search.google.com/search-console), adicione uma propriedade do tipo **prefixo de URL** com `https://lucas-jdev.github.io/pebacast/`. Escolha a verificação por **tag HTML** e copie só o valor do `content` para `site.verificacao.google` no `config/pipeline.yaml`. Faça o commit, espere o `site.yml` publicar e clique em *Verificar*. Depois, em *Sitemaps*, envie `sitemap.xml`.
2. **Bing Webmaster Tools.** Em [bing.com/webmasters](https://www.bing.com/webmasters), use **Importar do Google Search Console**, que reaproveita a verificação. Se preferir verificar à parte, use a meta tag e ponha o valor em `site.verificacao.bing`. Confira se o sitemap apareceu.
3. **Chave do IndexNow.** No Bing Webmaster Tools, em *IndexNow*, gere uma chave e ponha em `site.indexnow`. A chave não é segredo: o próprio site a publica em `<url_site>/<chave>.txt`, por desenho do protocolo.
4. **Primeiro aviso.** Rode o `site.yml` à mão (*Actions → Publicar site → Run workflow*) com **todas** marcado. Isso avisa todas as URLs do sitemap de uma vez, inclusive as que não têm `lastmod`, como a `sobre/`. Daí em diante, cada publicação avisa só o que mudou.
5. **Conferir.** Na inspeção de URL do Search Console e do Bing, `sobre/` deve aparecer como indexada. Isso leva de dias a semanas.

## QA do áudio

Depois de publicar, `src/podcast/qualidade_audio.py` mede o MP3 final com o ffmpeg (`ebur128` e `silencedetect`), sem ouvir:

| Medida | Como mede | Limite |
|---|---|---|
| Pico real | pico real (true peak) do episódio inteiro | ≤ −1,0 dBTP |
| Loudness integrada | EBU R128 do episódio inteiro | −16 LUFS ± 1 |
| Música (abertura e encerramento) | loudness do trecho só de música, na abertura e no encerramento, contra a da fala | não passa a da fala |
| Pausa na troca de blocos | silêncio (abaixo de −50 dBFS) que contém cada troca de bloco marcada pela montagem | ≤ 0,6 s |

As pausas no meio de um bloco são do TTS e não entram na conta. Os limites partem do alvo da montagem e ficam em `audio.qualidade`, em `config/pipeline.yaml`.

O resultado vai para o resumo da execução no Actions (`qualidade.md`). **O QA não segura a publicação.** Se alguma medida reprovar, o episódio sai assim mesmo e o Python abre uma issue `incidente` com as medidas, com o título `Áudio do <id> fora do padrão`. Se já houver uma aberta para o episódio, comenta nela. Quando o áudio daquele episódio passar, a issue fecha sozinha. Uma falha do próprio QA também não segura a publicação: vira aviso.

## Regravação do áudio

Quando um áudio publicado sai ruim, `.github/workflows/regravar.yml` narra o mesmo roteiro de novo, disparado à mão no Actions com o id do episódio:

1. **regravar** (`python -m podcast.regravacao regravar <id>`): valida o roteiro, narra só com o TTS principal, sem fallback, e anexa `pebacast-<id>-candidata.mp3` ao release, com as medidas do QA ao lado (`pebacast-<id>-candidata.qualidade.json`). O link e as quatro medidas aparecem no resumo da execução. O feed não muda, e a issue de incidente também não: a candidata ainda não está no ar.
2. **substituir** (`python -m podcast.regravacao substituir <id>`): põe a candidata no lugar do áudio publicado, atualiza tamanho, duração e `regravado_em` no `publicacao.json` e publica o feed. URL, GUID e data de publicação continuam os mesmos. Com as medidas da candidata, mostra o QA no resumo e atualiza a issue de incidente do episódio: fecha se passou, comenta se não.

Decisão em [ADR 0008](adr/0008-regravacao-em-dois-passos.md).

## Falhas

Qualquer falha abre uma issue no repositório, o que gera notificação por e-mail. Áudio fora do padrão também, mas sem segurar a publicação ([QA do áudio](#qa-do-áudio)). Isso também evita que o agendamento morra em silêncio. Ver [ADR 0003](adr/0003-agendamento-github-actions.md).

## Ciclo de feedback

Os arquivos em `feedback/<saga>/` entram no prompt do roteirista nos episódios seguintes da mesma saga. A pipeline só lê esses arquivos, nunca os altera.

## Critério de go/no-go para o Spotify

O feed vai para o Spotify quando, ao mesmo tempo:

- pelo menos 30 episódios tiverem sido publicados;
- os últimos 10 episódios com feedback não tiverem nenhum erro conceitual grave;
- a média das notas dos últimos 10 feedbacks for 4 ou mais.
