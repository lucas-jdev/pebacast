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

No aplicativo de podcast o áudio é a única interface, então o episódio diz ao ouvinte onde ele está e como responder (#112). Em roteiro novo, o `validar` também confere:

- **Aviso de IA:** a primeira fala traz, ao pé da letra, o `roteiro.aviso_ia` de `config/pipeline.yaml`, a mesma frase que abre as show notes.
- **Saga e posição:** as três primeiras falas dizem "terceiro episódio da saga Soluções", com o nome curto do site e a posição no currículo.
- **Próximo da saga:** as três últimas falas anunciam o tema do "próximo episódio da saga ...", sem prometer data, porque as sagas se revezam ("amanhã" reprova). No último episódio do currículo, não há o que anunciar.
- **Pedido de retorno:** as três últimas falas trazem o `roteiro.pedido_de_retorno`, que aponta para o link de votar nas show notes.

Roteiro já publicado fica fora dessas regras, para a regravação de um episódio anterior a elas continuar passando. A saudação variada e o tema do próximo são pedidos da rotina, e não do `validar`: a rotina recebe no contexto as aberturas dos últimos episódios e o título do próximo da saga.

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

Cada fala é sintetizada pelo `TtsProvider` configurado, com no máximo dois falantes por requisição. No Gemini, as falas vão no menor número de blocos que o limite de `tts.max_caracteres_por_bloco` permite, com tamanhos parecidos: encher um bloco de cada vez deixava a despedida sozinha num bloco de poucas centenas de caracteres, e sem contexto o Gemini mudava o timbre na última troca de voz (co-002). O silêncio que o TTS deixa nas bordas de cada bloco é aparado (abaixo de −50 dBFS, com 30 ms de folga) antes de os blocos serem emendados com a pausa fixa de 300 ms; sem isso, a troca de bloco chegava a 1,1 s de silêncio. A montagem guarda onde fica cada troca, para o QA medir. Cada bloco do Gemini tem até 4 tentativas, com espera exponencial a partir de 15 s, porque o free tier devolve 429 por minuto com frequência. Essa é a única camada de retentativa: o cliente do SDK é criado com a retentativa própria desligada (`HttpRetryOptions(attempts=1)`), para que cada tentativa apareça no log, e com um teto de tempo por requisição (`tts.gemini.timeout_s`, 180 s). Um 429 de cota **diária** esgotada (o `quotaId` cita `PerDay`; no free tier, 10 requisições por dia, e um episódio usa de 4 a 5) não é repetido, porque só renova no dia seguinte: vira `CotaDiariaEsgotada`, e o episódio aguarda a renovação em vez de ir para o fallback ([ADR 0011](adr/0011-cota-esgotada-espera.md)). Se o provedor principal ainda assim falhar, a pipeline usa o fallback e abre uma issue avisando. A decisão está em [ADR 0001](adr/0001-tts-gemini-com-fallback-kokoro.md).

## 7. Montagem

O ffmpeg mistura a fala com a vinheta e exporta em MP3 mono a 64 kbps, com cerca de 10 MB por episódio. Com a vinheta configurada, o recorte toca na abertura, por baixo da primeira fala, e no encerramento ([docs/vinheta.md](vinheta.md)).

- **Ganho único até −16 LUFS, na fala.** A fala inteira recebe um só ganho, calculado pela loudness medida. O loudnorm, usado antes, é dinâmico: puxava a música do encerramento, mais baixa que a fala, para o alvo.
- **Pico real limitado.** Depois do ganho, um limitador com a taxa quadruplicada (para enxergar o pico entre amostras) segura o pico real da fala em −1,5 dBTP. A fala é limitada **antes** da mistura com a vinheta, e um segundo limitador, com o mesmo teto, segura a soma (só a sobreposição da abertura chega perto dele).
- **Música nivelada pela fala, no MP3.** Cada recorte da vinheta entra com um volume próprio, `audio.vinheta.abaixo_da_fala_lu` (2 LU) abaixo do alvo de loudness, seja qual for o volume da faixa. Depois de codificar, a montagem mede a fala e a música no MP3, nos mesmos trechos que o QA do áudio mede, e corrige o volume do recorte que não ficou entre 2 e 2,5 LU abaixo da fala. Antes (#142), o recorte era nivelado pela fala crua e o ganho e o limitador vinham depois da mistura. O limitador baixava os picos da fala e quase não tocava a música, o laço da loudness subia o ganho de tudo para compensar, e a música subia junto. Além disso, a montagem nivelava o recorte inteiro, com o fade-out, e o QA mede a abertura só até a fala entrar, 0,4 LU mais alta. O si-003 saiu com a abertura 0,9 LU acima da fala. O codificador MP3 ainda sobe o pico e tira alguns décimos de LU, então a montagem mede o MP3 e, se precisar, codifica de novo com o teto mais baixo, o ganho e o volume da música corrigidos (até 5 passadas). Três não bastavam: no se-002, cada correção da loudness empurrou o pico de volta, o codificador sobe mais o pico quanto mais baixo fica o teto, e o episódio saiu com −0,7 dBTP.

## 8. Publicação

O MP3 vai para o `AudioStorage` (um release `episodio-<id>` por episódio) e o Actions commita `publicacao.json`. O `feed.xml` é regenerado inteiro a partir de `episodios/` e publicado no GitHub Pages, em https://lucas-jdev.github.io/pebacast/feed.xml. O deploy passa pela action local `.github/actions/deploy-pages-com-retentativa`, usada pelos três workflows que publicam no Pages: às vezes o GitHub ainda não lista o pacote do site recém-enviado ("No artifacts named github-pages", 2 vezes em 14 deploys em nov/2026, uma delas deixando o se-002 fora do feed), então ela espera 60 s e tenta mais uma vez com o mesmo pacote (#89). Ele traz:

- GUID imutável do episódio;
- show notes com o link da página do episódio para votar e deixar recado, as fontes, o desafio e o resumo do relatório de revisão;
- aviso de conteúdo gerado por IA.

Mudanças que só afetam o site ou o feed (`site/`, `src/podcast/site.py`, `src/podcast/publicacao.py`, `curriculum/`, `config/`) são publicadas por `.github/workflows/site.yml`, sem esperar episódio novo. Ele também pode ser disparado à mão. Ele faz checkout da ponta do `main`, e não do commit que o disparou: se ficou na fila esperando uma publicação de episódio, ele publica o `main` já com o episódio novo. Pelo mesmo motivo, `publicar.yml` e `regravar.yml` geram o site de novo depois do `git pull --rebase`, antes do deploy.

O site ganha uma página por episódio publicado em `episodios/<id>/`, e o `<link>` de cada item do feed aponta para ela. Essa URL não muda, e o id do episódio não é renomeado depois de publicado ([ADR 0010](adr/0010-url-permanente-do-episodio.md)).

Decisão de hospedagem em [ADR 0002](adr/0002-hospedagem-pages-releases.md).

### Avisos da publicação

O que sai diferente do normal sem segurar o episódio vira um aviso (`src/podcast/avisos.py`), e cada aviso diz se é de fallback de voz:

| Aviso | Vai para |
|---|---|
| Sintetizado com o fallback (Kokoro) | `avisos.md` → o `publicar.yml` abre "Episódio publicado com fallback de voz (<data>)" |
| Publicado sem vinheta | issue `incidente` "Avisos na publicação do <id>" |
| QA do áudio não rodou até o fim | idem |
| Issue da cota esgotada não foi aberta ou fechada | idem |

A issue de avisos é uma por episódio: um novo aviso no mesmo episódio só comenta nela. O título não termina em ": <id>" de propósito, para o passo "Atualizar issues" não fechá-la quando o episódio sai; quem fecha é o Lucas. O `relatorio.json` também separa os dois tipos (`avisos.fallback` e `avisos.outros`). O "QA de texto não rodou" fica fora dos avisos: vai só para o resumo e para um `::warning::`.

### Cota diária do Gemini esgotada

Com a cota do dia esgotada, o episódio não é publicado nem vai para o Kokoro ([ADR 0011](adr/0011-cota-esgotada-espera.md)). `src/podcast/espera_de_cota.py` grava `episodios/<id>/aguardando_cota.json` (`{"desde": ...}`, que não muda numa nova falha) e abre a issue `incidente` "Cota do Gemini esgotada: <id> aguardando", ou comenta na que já está aberta. O workflow commita o arquivo, e o site é publicado com o card "Próximo" avisando que o episódio sai em breve (o estado `AGUARDANDO_COTA` vale só para o site: para a seleção da rotina, o episódio continua aguardando publicação).

O `publicar.yml` também roda agendado, às 08:15 UTC, depois da renovação da cota. No agendamento, um job `verificar` roda `python -m podcast.publicacao aguardando`, que lista os episódios com `aguardando_cota.json` e sem `publicacao.json`, e a publicação só roda se houver algum. Um roteiro reprovado parado na pasta fica de fora: ele é tratado pelo push da rotina, e tentar de novo todo dia só repetiria o comentário na issue dele e publicaria o site sem nada novo. O `push` e o `workflow_dispatch` não passam pela verificação. Quando o episódio sai, o arquivo é apagado no mesmo commit do `publicacao.json`, e a issue fecha. Falhar ao abrir ou fechar a issue vira aviso e não segura nada.

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

## QA de texto

O QA do áudio não percebe quando o TTS fala outra coisa no lugar do roteiro ("a GPL" em vez de "a AGPL"). Depois do QA do áudio, `src/podcast/qualidade_texto.py` confere isso, em **modo aviso** (#69):

1. Recorta a fala do MP3 (`Trechos.fala`, sem a vinheta) em janelas de até `qualidade_texto.janela_maxima_s` (5 min), cortadas na troca de bloco mais tardia que cabe, e cada um dos dois modelos de `qualidade_texto.modelos` transcreve janela por janela. Um episódio de 16 minutos dá 4 janelas, 8 requisições. O episódio inteiro numa requisição só saía cortado: no se-002 (21/11), os dois modelos pararam em 69% do roteiro, e o resto virou uma divergência do tamanho do episódio. Cortar fora de uma troca de bloco só acontece se não houver nenhuma na janela, porque uma palavra cortada ao meio seria ouvida errada pelos dois modelos.
2. Normaliza o roteiro **original** (não o texto do dicionário de pronúncia) e cada transcrição: minúsculas, sem acento, sem pontuação e com as equivalências de fala de `qualidade_texto.equivalencias` ("pra" = "para", "pras" = "para as", "perai" = "pera aí"). Também não conta como divergência (#132): número por extenso transcrito como algarismo; a mesma fala com outra separação ("trade-off" e "tradeoff", "senão" e "se não"); e diferença feita só de artigo, preposição contraída, conjunção ou interjeição ("[] a", "[e] (nada)", "num" e "no"). "Não", "nem" e "sem" nunca entram nessa lista, porque um deles sumido inverte a frase. Nos 4 primeiros incidentes, isso tirou do laudo 25 das 43 divergências, e o erro real do sw-004 ("Nodewright" dito como "Nygard") ficou. Também não conta (#141): símbolo de caminho lido por extenso ("barra", "ponto", "traço", "underline", "arroba") quando a transcrição não traz nada no lugar, porque o roteiro diz "docs barra c4 traço negócio ponto md" e o transcritor escreve "docs/c4-negocio.md"; e o falado e o escrito do mesmo tempo de "estar" ("estar", "está" e "tá"; "estava" e "tava"; "estavam" e "tavam"; "estiver" e "tiver"). Um símbolo com outra palavra no lugar ("[ponto]" → "porto") e outro tempo do verbo ("estiver" → "estava") continuam contando, assim como singular e plural, flexão, palavra de conteúdo, nome próprio e negação. Nos 6 incidentes de texto abertos, isso tirou mais 19 das 49 divergências que ainda sobravam.
3. Alinha palavra por palavra (`difflib.SequenceMatcher`). Só conta a divergência que aparece **nas duas** transcrições, no mesmo trecho do roteiro: erro de um modelo só é ruído de transcrição. No teste do especial do Prumo, foi isso que separou erro real de ruído.
4. Se uma transcrição juntar menos de `qualidade_texto.cobertura_minima` (85%) das palavras do roteiro, ou o modelo parar no limite de tokens de saída, o QA de texto conta como "não rodou" em vez de reportar o que faltou como divergência. Divergências que caem no mesmo trecho do roteiro viram uma linha só, e um trecho com mais de 12 palavras aparece resumido.

O laudo vai para o resumo da execução (`qualidade.md`). Com divergência confirmada, o Python abre a issue `incidente` "Texto do <id> diverge do roteiro", ou comenta na aberta. O Lucas ouve cada trecho, marca na issue se o aviso acertou ou foi alarme falso e fecha à mão: é o que vai calibrar a regeneração automática (#70).

A transcrição usa a mesma camada única de retentativa do TTS (`src/podcast/retentativa.py`): 429 e 5xx esperam e tentam de novo, e um pedido recusado (4xx) desiste na hora. Se os modelos continuarem indisponíveis, o resumo diz "QA de texto não rodou", o log ganha um `::warning::` e a publicação segue. Essa falha **não** entra nos avisos: os modelos de áudio dão 503 com frequência, e ela abriria issue demais.

**Cota no free tier.** Os limites por dia ficam no painel do AI Studio, por modelo, e não em tabela pública (ADR 0001). A cota de cada modelo de transcrição é separada da do `gemini-3.8-flash-tts`, então o QA de texto não tira requisição da narração:

| Modelo | Requisições por dia (free tier) | Uso por episódio |
|---|---|---|
| `gemini-3.6-flash` | _conferir no AI Studio_ | 2 por janela, uma no QA de texto e outra no de pronúncia (cerca de 8) |
| `gemini-3.5-flash` | _conferir no AI Studio_ | 2 por janela, uma no QA de texto e outra no de pronúncia (cerca de 8) |

## QA de pronúncia

O QA de texto não percebe quando o TTS diz um termo do jeito errado: no co-002 (23/11), o Davi disse "Pebacast" com E fechado na abertura, e a transcrição saiu "Pebacast" do mesmo jeito. Depois do QA de texto, `src/podcast/qualidade_pronuncia.py` confere isso, em **modo aviso** (#107):

1. Separa os termos de `tts.pronuncia` que têm `instrucao` e aparecem no roteiro **original**, com o mesmo casamento do dicionário. A instrução é o critério, então o dicionário continua sendo a única fonte. Sem nenhum desses termos, não faz requisição.
2. Recorta a fala nas mesmas janelas do QA de texto (`qualidade_pronuncia.janela_maxima_s`, 5 min) e manda cada janela aos dois modelos de `qualidade_pronuncia.modelos`, pedindo JSON num esquema fixo: para cada vez que ouviu um termo, o segundo aproximado na janela, o veredito (`certo` ou `errado`) e como soou. Uma resposta com termo fora da lista ou veredito fora do esquema conta como inválida.
3. Só conta o erro que **os dois** modelos marcam no mesmo termo e na mesma janela.

O laudo vai para o resumo da execução (`qualidade.md`) com a contagem por termo, mesmo aprovado: quantas vezes o roteiro diz o termo e quantas cada modelo ouviu, certas e erradas. Ouvir menos vezes do que o roteiro diz significa que o QA não julgou aquelas ocorrências, e é o que separa "sem erro" de "não ouviu". Com erro confirmado, o Python abre a issue `incidente` "Pronúncia do <id> diverge do dicionário", ou comenta na aberta, com o instante aproximado no MP3 e o que cada modelo ouviu. O Lucas ouve, marca se o aviso acertou e fecha à mão.

As falhas seguem o QA de texto: a mesma retentativa, a resposta cortada no limite de tokens conta como "não rodou", e "QA de pronúncia não rodou" vai só para o resumo e para um `::warning::`, fora dos avisos.

**Calibração.** Um modelo de áudio pode não distinguir E aberto de fechado, e a confirmação por dois modelos reduz o falso positivo, não o falso negativo. Para calibrar num MP3 já publicado, como o original do co-002, que o Lucas ouviu errado:

```bash
python -m podcast.qualidade_pronuncia pebacast-co-002-anterior.mp3 episodios/co-002/roteiro.json
```

## Regravação do áudio

Quando um áudio publicado sai ruim, `.github/workflows/regravar.yml` narra o mesmo roteiro de novo, disparado à mão no Actions com o id do episódio:

1. **regravar** (`python -m podcast.regravacao regravar <id>`): valida o roteiro, narra só com o TTS principal, sem fallback, e anexa `pebacast-<id>-candidata.mp3` ao release, com as medidas do QA ao lado (`pebacast-<id>-candidata.qualidade.json`). O link, as quatro medidas e o laudo do [QA de pronúncia](#qa-de-pronúncia) da candidata aparecem no resumo da execução. O QA de pronúncia não abre issue aqui, e se não rodar o passo continua, porque a candidata já foi anexada. O feed não muda, e a issue de incidente também não: a candidata ainda não está no ar.
2. **substituir** (`python -m podcast.regravacao substituir <id>`): guarda o áudio que está no ar como `pebacast-<id>-anterior.mp3` no release, que serve de caminho de volta e de caso de calibração dos QAs, e só então põe a candidata no lugar do áudio publicado. Depois atualiza tamanho, duração e `regravado_em` no `publicacao.json` e publica o feed. URL, GUID e data de publicação continuam os mesmos. Com as medidas da candidata, mostra o QA no resumo e atualiza a issue de incidente do episódio: fecha se passou, comenta se não.

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
