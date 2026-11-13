# Pebacast

Se você é a rotina do roteirista, siga `rotina/roteirista.md` e ignore este arquivo: ele vale para quem muda o código.

## Documentação que anda junto com o código

Uma mudança que altera o fluxo do episódio ou a arquitetura atualiza os documentos **no mesmo commit**:

- `docs/fluxo-do-episodio.md`: etapas, decisões e desvios, do agendamento ao app de podcast.
- `docs/c4-negocio.md`: atores, sistemas externos, contêineres e suas relações.

Exemplos que exigem a atualização: etapa nova ou removida, mudança em quem executa (humano, IA ou código), serviço externo novo, nova regra de falha ou fallback, novo workflow. Refatoração interna sem efeito no fluxo não exige.

Os diagramas são Mermaid. Antes de commitar, renderize e confira o resultado: dentro de `subgraph`, não use `direction`, porque as setas passam a apontar para a borda do grupo em vez do bloco. Decisões de arquitetura novas viram ADR em `docs/adr/`.

## Verificação

- Python: `.venv/bin/python -m pytest -q`
- API de votos: `cd votos && node --test`
