# 0007. Curti / não curti com Cloudflare Worker e D1

- Status: Aceito
- Data: 2026-11-12

## Contexto

O Lucas quer um "curti / não curti" por episódio no site, guardado em algo como SQLite. O site é estático no GitHub Pages (ADR 0002), sem servidor para receber o voto. O voto também precisa ser útil: é o primeiro retorno de quem ouve sobre o que a pipeline produz.

Restrições: seguir o design system, não poluir o card e não piorar performance nem acessibilidade.

## Opções consideradas

- **Cloudflare Worker + D1.** O D1 é SQLite gerenciado. No plano gratuito, a cota diária de requisições sobra para o volume do podcast. É serviço novo, mas é uma função de ~50 linhas, sem servidor para manter.
- **Supabase / Turso.** Funcionam, mas expõem uma chave e regras de acesso no navegador, ou exigem uma função na frente do mesmo jeito.
- **Giscus / reações de Discussions.** Exige login no GitHub e carrega um iframe pesado: piora o LCP e afasta quem só ouve.
- **Evento no GoatCounter.** Zero infra, mas não dá para trocar ou desfazer o voto nem ler o placar de forma limpa.

## Decisão

Worker `pebacast-votos` (pasta `votos/`) com uma tabela no D1:

- `POST /votos` com `{"episodio": "si-001", "voto": "curti" | "nao_curti" | null}`. Grava um voto por visitante e episódio: votar de novo troca o voto, `null` apaga.
- `GET /votos` devolve o placar público por episódio, com cache de 60 s. É o insumo para a pipeline levar o retorno em conta.
- **Visitante = HMAC-SHA256 do IP com um sal que só existe na Cloudflare.** O IP nunca é gravado. Sem cookie, coerente com o GoatCounter.
- **Corpo em `text/plain`:** é um pedido simples de CORS, sem preflight. O POST só é aceito com `Origin` do site.

No site:

- Os botões só são renderizados com `site.votos_api` configurado. Sem JS, o CSS os esconde, como faz com o player customizado. A classe `.js` é aplicada antes da pintura, então não há layout shift.
- **Nenhuma requisição no carregamento.** O estado do botão vem do `localStorage`, e a rede só é usada no clique. O placar não aparece no site: com pouca audiência, "0 curtidas" seria ruído.
- Os botões usam `aria-pressed`, alvo de 44 px e status anunciado em região `role="status"`. A atualização é otimista: em caso de erro, o botão volta ao estado anterior e a mensagem aparece na tela.

## Consequências

- Um provedor a mais (Cloudflare). O deploy é pelo workflow `votos.yml`, e o id do banco é resolvido na conta a cada deploy, sem ficar no repositório.
- Um voto por IP: quem divide rede (casa, empresa) divide o voto, e quem troca de rede vota de novo. Para sinal de qualidade de um podcast pequeno, isso basta. Não é uma enquete.
- Próximo passo natural: a rotina do roteirista lê o `GET /votos` antes de escrever.
