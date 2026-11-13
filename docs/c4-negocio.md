# Modelo C4 do Pebacast

Dois níveis do [modelo C4](https://c4model.com): o **contexto**, que mostra quem usa o Pebacast e do que ele depende, e os **contêineres**, que mostram as partes que entregam esse valor. Os níveis de componente e de código ficam no próprio código (`src/podcast/`, `votos/`).

## Nível 1 · Contexto

O Pebacast entrega todo dia uma conversa de 15 a 20 minutos sobre arquitetura de software, seguindo um currículo em 7 sagas. Os roteiros são escritos e revisados por IA, contra referências que o Lucas verificou.

```mermaid
flowchart TB
    classDef pessoa fill:#15110c,stroke:#15110c,color:#efe4c8
    classDef sistema fill:#f2c53d,stroke:#15110c,color:#15110c,stroke-width:3px
    classDef externo fill:#efe4c8,stroke:#15110c,color:#15110c

    ouvinte["<b>Ouvinte</b><br/>[pessoa]<br/>dev que quer evoluir<br/>em arquitetura"]:::pessoa
    lucas["<b>Lucas</b><br/>[pessoa]<br/>curador: monta o currículo,<br/>verifica referências, lê o retorno"]:::pessoa

    pebacast["<b>Pebacast</b><br/>[sistema]<br/>escreve, revisa, narra e publica<br/>um episódio por dia"]:::sistema

    claude["<b>Claude</b><br/>[sistema externo]<br/>roteirista e revisor"]:::externo
    noticias["<b>Fontes na web</b><br/>[sistema externo]<br/>notícias e referências"]:::externo
    gemini["<b>Gemini API</b><br/>[sistema externo]<br/>voz das personas"]:::externo
    apps["<b>Apps de podcast</b><br/>[sistema externo]<br/>AntennaPod, Spotify"]:::externo

    ouvinte -- "ouve episódios" --> apps
    apps -- "assinam o feed RSS" --> pebacast
    ouvinte -- "lê transcrição, vota<br/>e manda recado pelo site" --> pebacast
    lucas <-- "cura o currículo e as referências;<br/>recebe votos, recados e issues" --> pebacast
    pebacast -- "pede roteiro e revisão" --> claude
    claude -- "busca notícia e<br/>checa afirmações" --> noticias
    pebacast -- "sintetiza o diálogo" --> gemini
```

| Elemento | Valor para o negócio |
|---|---|
| Ouvinte | Aprende arquitetura em doses diárias, a partir de casos reais e com o raciocínio dos trade-offs. |
| Lucas | Controla o que é ensinado (currículo e referências) sem escrever cada episódio. |
| Claude | Escala a escrita, e a revisão independente reduz o risco de afirmação errada. |
| Gemini API | Dá vozes distintas às personas. Sem ela, o fallback local sustenta a publicação, com qualidade menor. |
| Apps de podcast | Distribuição sem custo, pelo padrão RSS. |

## Nível 2 · Contêineres

```mermaid
flowchart TB
    classDef pessoa fill:#15110c,stroke:#15110c,color:#efe4c8
    classDef ia fill:#cdb8ea,stroke:#15110c,color:#15110c
    classDef conteiner fill:#a9c8ec,stroke:#15110c,color:#15110c
    classDef dados fill:#c6dc8e,stroke:#15110c,color:#15110c
    classDef externo fill:#efe4c8,stroke:#15110c,color:#15110c

    lucas["<b>Lucas</b><br/>[pessoa]"]:::pessoa
    ouvinte["<b>Ouvinte</b><br/>[pessoa]"]:::pessoa

    revisor["<b>Revisor</b><br/>[subagente Claude]<br/>checa afirmações,<br/>sem o contexto do roteirista"]:::ia
    rotina["<b>Rotina do roteirista</b><br/>[Claude Code agendado]<br/>seleciona, busca notícia,<br/>escreve e corrige"]:::ia
    watchdog["<b>Watchdog</b><br/>[GitHub Actions, a cada 6 h]<br/>avisa se a rotina parar"]:::conteiner

    repo[("<b>Repositório</b><br/>[GitHub]<br/>currículo, personas, roteiros,<br/>revisões e publicações")]:::dados

    pipeline["<b>Pipeline de publicação</b><br/>[GitHub Actions + Python]<br/>valida, narra, mixa e publica"]:::conteiner
    gemini["<b>Gemini API</b><br/>[externo]"]:::externo

    audio[("<b>Áudios</b><br/>[GitHub Releases]<br/>MP3 de cada episódio")]:::dados
    site["<b>Site e feed</b><br/>[GitHub Pages]<br/>HTML estático e feed.xml"]:::conteiner
    votos[("<b>API de votos</b><br/>[Cloudflare Worker + D1]<br/>votos e recados")]:::dados

    apps["<b>Apps de podcast</b><br/>[externo]"]:::externo
    goat["<b>GoatCounter</b><br/>[externo]<br/>visitas, sem cookie"]:::externo

    lucas -- "edita currículo,<br/>verifica referências" --> repo
    rotina <-- "pede revisão" --> revisor
    rotina -- "lê o contexto e<br/>commita o episódio" --> repo
    watchdog -. "observa commits" .-> repo
    repo -- "push dispara" --> pipeline
    pipeline -- "narra" --> gemini
    pipeline -- "sobe o MP3" --> audio
    pipeline -- "gera e publica" --> site
    site -- "voto e recado" --> votos
    site -- "visitas" --> goat
    apps -- "leem o feed" --> site
    apps -- "baixam o MP3" --> audio
    ouvinte -- "ouve" --> apps
    ouvinte -- "navega" --> site
```

Lilás é IA (Claude), azul é código (GitHub Actions e site estático), verde é onde os dados ficam e bege são serviços de terceiros. O único humano no desenho é o Lucas, que entra pelo repositório (currículo e referências) e pelo retorno. O Lucas lê os recados pelo console do D1 ([votos.md](votos.md)), e o Pipeline registra o `publicacao.json` de volta no repositório.

### Decisões que este desenho carrega

- **O repositório é a fonte da verdade.** O estado de cada episódio vem dos arquivos (`roteiro.json`, `revisoes/`, `publicacao.json`), não de um banco, e todo passo fica auditável no histórico ([ADR 0006](adr/0006-roteiro-por-rotina-claude.md)).
- **Julgamento separado de execução mecânica.** A IA escreve; o Actions não confia nela e valida de novo antes de gastar voz.
- **Custo zero de hospedagem.** Pages, Releases, Actions e o plano gratuito da Cloudflare ([ADR 0002](adr/0002-hospedagem-pages-releases.md), [ADR 0007](adr/0007-votos-worker-d1.md)).
- **Único dado dinâmico fora do GitHub:** votos e recados. O site estático continua sem servidor.
