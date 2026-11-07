# 0002. Feed no GitHub Pages e áudio no GitHub Releases

- Status: Aceito
- Data: 2026-11-05

## Contexto

Cada episódio gera um MP3 mono a 64 kbps de cerca de 10 MB, o que dá aproximadamente 3,5 GB por ano. A publicação precisa ser automatizável por API, gratuita e com URL estável, porque a URL do feed vai para o Spotify depois da homologação.

Dados conferidos em 2026-11-05.

## Decisão

- O `feed.xml` é servido pelo GitHub Pages.
- Os MP3 são publicados como assets do GitHub Releases, um release por episódio.
- O armazenamento de áudio fica atrás da interface `AudioStorage`.
- O repositório é público.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| Áudio dentro do GitHub Pages | Mais simples | Site publicado limitado a 1 GB (cerca de 100 episódios), e binários incham o histórico do Git |
| Cloudflare R2 | 10 GB grátis, saída de dados gratuita, API S3 | Cota estoura em cerca de 3 anos e passa a cobrar. Fica como destino de migração |
| Hospedar no Spotify for Creators | Grátis | Sem API de upload, inviabiliza a automação |

## Consequências

Positivas:

- Custo zero, sem limite prático de armazenamento e automação com a CLI `gh`.
- A interface `AudioStorage` permite migrar para o R2 sem alterar o gerador do feed.

Negativas:

- O repositório precisa ser público: o GitHub Pages gratuito só funciona em repositório público, e assets de release em repositório privado exigem autenticação para download. O MVP privado é, na prática, não divulgado.
- O GitHub Releases não é uma CDN de mídia. Testar a reprodução no AntennaPod antes de considerar a decisão validada.

## Regras que esta decisão cria

1. A URL do feed é um contrato público. Ela é definida no primeiro episódio e nunca muda.
2. O GUID de um episódio é derivado do `id` do spec e nunca muda, mesmo que o áudio seja regenerado.
3. Se for preciso mudar de host do feed, usar a tag `itunes:new-feed-url` e manter o feed antigo redirecionando.

## Critério de revisão

Revisar se o repositório passar de 5 GB, se o GitHub restringir o uso de releases para mídia ou na ida para o Spotify.

## Fontes

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [R2 pricing (FlareCalc)](https://flarecalc.com/calculators/r2)
- [Claiming your podcast on Spotify for Creators](https://support.spotify.com/ie/creators/article/claiming-your-podcast-on-spotify-for-creators)
