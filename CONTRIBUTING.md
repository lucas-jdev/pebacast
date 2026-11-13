# Contribuindo com o Pebacast

Valeu pelo interesse! O backlog é público e fica nas issues. O processo inteiro está em [docs/backlog.md](docs/backlog.md).

## Tem uma ideia ou achou um bug?

Abra uma issue pelos formulários *Ideia* ou *Bug*. Não precisa vir pronta: lapidar a ideia faz parte do processo.

## Quer implementar?

1. Escolha uma issue com o label [`pronta`](../../issues?q=is%3Aopen+label%3Apronta). As outras ainda estão sendo lapidadas e podem mudar.
2. Comente na issue que vai pegar, para ninguém duplicar esforço.
3. Faça um fork, crie um branch e implemente seguindo os critérios de aceite da issue.
4. Atualize a documentação listada na issue no mesmo PR. Mudanças no fluxo do episódio ou na arquitetura atualizam `docs/fluxo-do-episodio.md` e `docs/c4-negocio.md`.
5. Rode os testes:
   ```
   python -m pytest -q
   cd votos && node --test
   ```
6. Abra o PR com `Closes #<número>` na descrição.

## Estilo

- O código e a documentação são em português.
- O código se explica sozinho: comente só o porquê que o código não consegue dizer, nunca o quê.
- Uma decisão de arquitetura nova vira ADR em `docs/adr/`.
