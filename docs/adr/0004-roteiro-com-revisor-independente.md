# 0004. Roteiro com revisor independente e contexto de notícias em cascata

- Status: Aceito
- Data: 2026-11-05
- Revisado: 2026-11-07. Roteirista e revisor rodam numa rotina do Claude Opus 5.5, e o revisor é um subagente sem o contexto do roteirista. Ver [ADR 0006](0006-roteiro-por-rotina-claude.md).

## Contexto

O ouvinte do MVP também é o aprendiz, então não tem como pegar um erro conceitual durante a escuta. Um LLM que escreve com base no que "lembra" de um livro pode inventar capítulos, citações e dados. Além disso, o episódio fica mais concreto quando ancorado num acontecimento real.

## Decisão

1. **Curadoria como gate.** Cada episódio aponta fonte e capítulo, e só é gerado com `referencias_verificadas: true`.
2. **Notícias em cascata.** Buscar em janelas de 7, 30 e 60 dias. Uma notícia só é aceita com nota de relevância mínima de 7 em 10. Se nenhuma passar, usar um cenário hipotético, declarado como hipotético no áudio. Notícias já usadas ficam registradas e não se repetem.
3. **Revisor separado do roteirista.** O revisor extrai as afirmações verificáveis e devolve um relatório com veredito por afirmação. Ele não reescreve o roteiro. O roteirista aplica as correções.
4. **Limite de ciclos e falha fechada.** No máximo dois ciclos de revisão. Se o roteiro continuar reprovado, o episódio não é publicado.

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Revisor que corrige o roteiro diretamente | Mistura duas responsabilidades. O revisor tende a quebrar o fluxo do diálogo e a corrigir o que não estava errado. É o mesmo motivo pelo qual, em code review, quem revisa comenta e o autor corrige |
| Sem revisor, só curadoria | A curadoria garante a fonte, não a fidelidade do que foi dito sobre ela |
| Usar qualquer notícia encontrada | Sem limiar de relevância, o modelo força conexões fracas entre a notícia e o tema |

## Consequências

Positivas:

- O relatório de revisão vira dado: dá para ver que tipo de erro o roteirista mais comete e ajustar os prompts.
- A falha fechada protege o objetivo principal, que é aprender certo.

Negativas:

- Roteirista e revisor no mesmo modelo compartilham pontos cegos. A mitigação é dar ao revisor um contexto diferente (referências do spec e busca) e um formato de saída diferente (vereditos, não texto).
- Cada episódio consome mais trabalho do modelo: até 3 buscas de notícia, 3 revisões e 2 correções.
- Alguns dias podem ficar sem episódio.

## Critério de revisão

Revisar se mais de 20% dos episódios de um mês falharem na revisão, ou se um erro grave aparecer no feedback de um episódio aprovado pelo revisor.
