# Pebacast

Se você é a rotina do roteirista, siga `rotina/roteirista.md` e ignore este arquivo: ele vale para quem muda o código.

## Documentação que anda junto com o código

Uma mudança que altera o fluxo do episódio ou a arquitetura atualiza os documentos **no mesmo commit**:

- `docs/fluxo-do-episodio.md`: etapas, decisões e desvios, do agendamento ao app de podcast.
- `docs/c4-negocio.md`: atores, sistemas externos, contêineres e suas relações.

Exemplos que exigem a atualização: etapa nova ou removida, mudança em quem executa (humano, IA ou código), serviço externo novo, nova regra de falha ou fallback, novo workflow. Refatoração interna sem efeito no fluxo não exige.

Os diagramas são Mermaid. Antes de commitar, renderize e confira o resultado: dentro de `subgraph`, não use `direction`, porque as setas passam a apontar para a borda do grupo em vez do bloco. Decisões de arquitetura novas viram ADR em `docs/adr/`.

## PRs que mudam o visual do site

Todo PR que muda algo visível no site (`site/`, `src/podcast/site.py`) leva prints de antes e depois na descrição, no desktop e no celular, para quem revisa julgar sem baixar o branch.

1. Gere os prints com `scripts/prints.sh <pasta>`, uma vez no `main` e outra no branch do PR, e recorte o trecho que mudou.
2. A API do GitHub não sobe imagem em PR. Commite os recortes no branch órfão `prints`, na pasta `pr-<número>/`, nunca no branch do PR.
3. Referencie pela URL `https://raw.githubusercontent.com/lucas-jdev/pebacast/prints/pr-<número>/<arquivo>.png`, numa tabela Antes | Depois, e confira que as imagens abrem.

## Verificação

- Python: `.venv/bin/python -m pytest -q`
- API de votos: `cd votos && node --test`
