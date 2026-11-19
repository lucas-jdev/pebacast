# Pebacast

Se você é a rotina do roteirista, siga `rotina/roteirista.md` e ignore este arquivo: ele vale para quem muda o código.

## Documentação que anda junto com o código

Uma mudança que altera o fluxo do episódio ou a arquitetura atualiza os documentos **no mesmo commit**:

- `docs/fluxo-do-episodio.md`: etapas, decisões e desvios, do agendamento ao app de podcast.
- `docs/c4-negocio.md`: atores, sistemas externos, contêineres e suas relações.

Exemplos que exigem a atualização: etapa nova ou removida, mudança em quem executa (humano, IA ou código), serviço externo novo, nova regra de falha ou fallback, novo workflow. Refatoração interna sem efeito no fluxo não exige.

Os diagramas são Mermaid. Antes de commitar, renderize e confira o resultado: dentro de `subgraph`, não use `direction`, porque as setas passam a apontar para a borda do grupo em vez do bloco. Decisões de arquitetura novas viram ADR em `docs/adr/`.

## PRs que mudam o visual do site

Todo PR que muda algo visível no site (`site/`, `src/podcast/site.py`) leva prints de antes e depois, no desktop e no celular, para quem revisa julgar sem baixar o branch.

**O comentário automático cumpre essa regra.** Em PR que muda `site/**` ou `src/podcast/site.py`, os workflows **Capturar prints** e **Comentar prints** ([ADR 0009](docs/adr/0009-prints-automaticos-nos-prs.md)) fotografam cada seção de `index.html`, `episodios.html`, `sobre/` e de uma página de episódio no `main` e no PR, e comentam no PR uma tabela Antes | Depois só das seções que mudaram (ou "Nenhuma mudança visual nas páginas capturadas"). Não precisa repetir os prints na descrição; confira que as imagens do comentário abrem.

Só faça à mão o que o comentário não cobre (outra página, tema escuro, ou o comentário não veio):

1. Gere os prints com `scripts/prints.sh <pasta>` (precisa do extra `prints`: `pip install -e ".[prints]"` e `python -m playwright install chromium`), uma vez no `main` e outra no branch do PR. Ele grava um PNG por seção; `python scripts/prints.py comparar <main> <branch> --saida <pasta>` separa as que mudaram.
2. A API do GitHub não sobe imagem em PR. Commite os prints no branch órfão `prints`, na pasta `pr-<número>/`, nunca no branch do PR.
3. Referencie pela URL `https://raw.githubusercontent.com/lucas-jdev/pebacast/prints/pr-<número>/<arquivo>.png`, numa tabela Antes | Depois, e confira que as imagens abrem.

## Verificação

- Python: `.venv/bin/python -m pytest -q`
- API de votos: `cd votos && node --test`
