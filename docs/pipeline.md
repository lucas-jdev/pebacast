# Pipeline de geração

Roda uma vez por dia, na noite anterior ao episódio. Cada etapa grava sua saída em `episodios/<id>/`, o que deixa a geração auditável: dá para ver de onde veio cada fala e o que o revisor corrigiu.

A pipeline tem duas partes, ligadas por um commit ([ADR 0006](adr/0006-roteiro-por-rotina-claude.md)):

```
Rotina do Claude (rotina/roteirista.md)                     GitHub Actions
seleção → notícias → roteiro → revisão ⇄ correção  ──push──▶  validar → voz → montagem → publicação
```

Arquivos de cada episódio:

| Arquivo | Quem grava | Conteúdo |
|---|---|---|
| `noticia.json` | rotina | notícia usada ou cenário hipotético |
| `roteiro.json` | rotina | diálogo final |
| `revisoes/1.json`, `2.json`, ... | subagente revisor | relatório de cada revisão |
| `publicacao.json` | Actions | GUID, URL do MP3 e data. Marca o episódio como publicado |

## 1. Seleção do episódio

`python -m podcast.roteiro contexto` escolhe, na ordem do currículo, o próximo episódio não publicado da saga do dia (definida em `config/pipeline.yaml`), cujos pré-requisitos já foram publicados e cujas referências estão verificadas. Se algum episódio já tem roteiro aprovado e ainda não foi publicado, nada novo é escrito.

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

O roteirista recebe o spec, as personas, o contexto de notícias e os feedbacks recentes e devolve o diálogo em JSON. O campo `estilo` de cada fala é opcional e vai para o TTS:

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

Cada fala é sintetizada pelo `TtsProvider` configurado, com no máximo dois falantes por requisição. Cada bloco do Gemini tem até 4 tentativas, com espera exponencial a partir de 15 s, porque o free tier devolve 429 com frequência. Se o provedor principal ainda assim falhar, a pipeline usa o fallback e abre uma issue avisando. A decisão está em [ADR 0001](adr/0001-tts-gemini-com-fallback-kokoro.md).

## 7. Montagem

O ffmpeg concatena as falas, normaliza o volume com loudnorm e exporta em MP3 mono a 64 kbps, com cerca de 10 MB por episódio. Com a vinheta configurada, o recorte toca na abertura, por baixo da primeira fala, e no encerramento ([docs/vinheta.md](vinheta.md)).

## 8. Publicação

O MP3 vai para o `AudioStorage` (um release `episodio-<id>` por episódio) e o Actions commita `publicacao.json`. O `feed.xml` é regenerado inteiro a partir de `episodios/` e publicado no GitHub Pages, em https://lucas-jdev.github.io/pebacast/feed.xml. Ele traz:

- GUID imutável do episódio;
- show notes com as fontes, o desafio e o resumo do relatório de revisão;
- aviso de conteúdo gerado por IA.

Mudanças que só afetam o site ou o feed (`site/`, `src/podcast/site.py`, `src/podcast/publicacao.py`, `curriculum/`, `config/`) são publicadas por `.github/workflows/site.yml`, sem esperar episódio novo. Ele também pode ser disparado à mão.

Decisão de hospedagem em [ADR 0002](adr/0002-hospedagem-pages-releases.md).

## Falhas

Qualquer falha abre uma issue no repositório, o que gera notificação por e-mail. Isso também evita que o agendamento morra em silêncio. Ver [ADR 0003](adr/0003-agendamento-github-actions.md).

## Ciclo de feedback

Os arquivos em `feedback/<saga>/` entram no prompt do roteirista nos episódios seguintes da mesma saga. A pipeline só lê esses arquivos, nunca os altera.

## Critério de go/no-go para o Spotify

O feed vai para o Spotify quando, ao mesmo tempo:

- pelo menos 30 episódios tiverem sido publicados;
- os últimos 10 episódios com feedback não tiverem nenhum erro conceitual grave;
- a média das notas dos últimos 10 feedbacks for 4 ou mais.
