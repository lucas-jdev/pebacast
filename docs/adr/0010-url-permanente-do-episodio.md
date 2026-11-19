# 0010. URL permanente do episódio: `episodios/<id>/`

- Status: Aceito
- Data: 2026-11-19

## Contexto

Até aqui, os episódios só existiam como âncoras dentro de duas páginas (`index.html#sw-002`, `episodios.html#sw-002`). Nenhum episódio tinha título, descrição ou URL próprios. Isso limitava a busca e as IAs, que não tinham um endereço para citar um episódio, e o compartilhamento, que mandava para o meio de uma lista longa. O épico #30 (SEO e GEO) pediu uma página por episódio (#45).

Uma URL publicada é um contrato: ela vai para buscadores, para respostas de IA, para mensagens compartilhadas e para o `<link>` de cada item do feed. Trocar o formato depois quebra todos esses links. E o GitHub Pages não faz redirecionamento 301, então não há como corrigir isso depois.

Em paralelo, a investigação de HX (#5) ainda vai escolher como o episódio é identificado no texto e no áudio: nome da saga e posição ("Saga Software · ep. 2"), sigla e número ("SW 002") ou outra forma.

## Decisão

A página de cada episódio publicado mora em `episodios/<id>/`, com o id técnico do currículo (`sw-002`), e esse caminho não muda.

- A URL é **desacoplada** do identificador de HX. O que se lê e se fala fica no `<title>`, no H1 e na etiqueta, e pode mudar à vontade sem quebrar nenhum link.
- **O id de um episódio não é renomeado depois de publicado.** Ele já era a base do GUID no feed (ADR 0002), e agora também é a base da URL.
- O caminho sai de um lugar só, `caminho_do_episodio` em `site.py`, usado pelo site, pelo sitemap e pelo feed.
- Pasta com `index.html`, e não `<id>.html`, para a URL não carregar extensão. É o mesmo formato da `sobre/`.
- As âncoras antigas (`episodios.html#<id>`) continuam valendo, porque o arquivo segue com todos os episódios.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| Título no slug (`episodios/sw-002-modularidade-coesao/`) | Palavra-chave na URL | Renomear o episódio quebraria a URL, e o ganho de SEO com slug é pequeno |
| Esperar o identificador da #5 (`software/2/`) | URL igual ao que se fala | Prende uma decisão permanente a uma investigação ainda aberta |
| Número global (`episodios/4/`) | Curto | Não diz a saga e briga com a ordem por saga |

## Consequências

Positivas:

- Cada episódio, com a transcrição e as fontes conferidas, ganha um endereço que buscadores e IAs podem citar e que dá para compartilhar.
- O feed passa a ter `<link>` por item, e os apps e diretórios de podcast mandam para a página do episódio.

Negativas:

- ~~Enquanto a transcrição também aparecer nas listas, o mesmo texto existe em duas URLs.~~ Resolvido em 19/11 (#55): a transcrição fica só na página do episódio, e as listas levam a ela por `episodios/<id>/#transcricao`. Era 75% do peso do `episodios.html`.
- Renomear um id passa a ser proibido na prática. Um episódio que mude de saga ganha um id novo e vira outro episódio.
