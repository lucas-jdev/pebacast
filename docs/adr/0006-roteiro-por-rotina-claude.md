# 0006. Roteiro escrito por rotina agendada do Claude, áudio pelo GitHub Actions

- Status: Aceito
- Data: 2026-11-07

## Contexto

A pipeline tem uma parte que pede julgamento (escolher a notícia, escrever o diálogo, verificar afirmações e corrigir) e uma parte mecânica (sintetizar, montar e publicar). O plano original, nos ADRs 0003 e 0004, rodava tudo num só workflow do GitHub Actions, chamando LLMs por API. Ainda faltava escolher o modelo.

O Lucas quer o Claude Opus 5.5 como roteirista, acionado por agendamento, com a revisão feita por um subagente sem o contexto de quem escreveu.

## Decisão

Separar a pipeline em duas partes, ligadas por um commit:

```
Rotina agendada (Claude Code na nuvem, Opus 5.5)        GitHub Actions
seleção → notícia → roteiro ⇄ subagente revisor         validar → voz → montagem → publicação
                         └── commit em episodios/<id>/ ──┘ (disparado pelo push)
```

1. **A rotina** roda toda noite e segue `rotina/roteirista.md`. Ela chama `python -m podcast.roteiro contexto` para saber o que escrever, busca a notícia na web, escreve o roteiro e pede a revisão.
2. **O revisor** é um subagente novo a cada revisão. Ele recebe só o caminho da pasta e as instruções de `rotina/revisor.md`, e não vê o raciocínio do roteirista.
3. **Tudo é commitado,** aprovado ou não, direto na `main`. A tentativa reprovada também é registro.
4. **O Actions não confia na rotina.** Ele roda `python -m podcast.roteiro validar` de novo. Se aprovar, sintetiza e publica. Se não, abre uma issue.
5. **O estado vem dos arquivos.** Um episódio está publicado quando `episodios/<id>/publicacao.json` existe, e aguarda publicação quando o roteiro passa no `validar`. O campo `status` saiu do currículo.

### Garantias do `validar`

- O relatório da última revisão traz o `roteiro_sha256` do roteiro que o revisor leu. Se o roteiro mudar depois da aprovação, a validação reprova.
- No máximo `max_ciclos + 1` revisões: cada ciclo é uma revisão seguida de correção, e a última correção precisa de uma revisão final. Com `max_ciclos: 2`, são até 3 revisões.
- Uma revisão marcada como aprovada não pode ter afirmação `incorreta` ou `imprecisa`. A última revisão precisa ter verificado pelo menos uma afirmação, e cada afirmação precisa apontar para uma fala que existe.
- A primeira fala é do apresentador e traz o aviso de IA. As personas são só o apresentador e o expert da saga. O tamanho fica dentro de `palavras_alvo`.
- A notícia tem nota de relevância mínima e não repete a de um episódio já publicado.

### Um episódio em produção por vez

Enquanto um roteiro aprovado não for publicado, a rotina não escreve outro. Se a publicação quebrar, os roteiros não se acumulam, e a rotina para com uma mensagem clara.

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Tudo no Actions, com Gemini por API | Faltava um modelo para roteirista e revisor. Também exigiria escrever em Python o laço de busca, escrita e revisão, que uma rotina do Claude já faz com ferramentas nativas |
| Tudo no Actions, com a API da Anthropic | Cobrança por token, além do plano já pago. Mesmo trabalho de orquestração |
| Rotina que só commita o que for aprovado | Uma falha ficaria invisível. Commitando tudo, o Actions vira o ponto único que abre a issue |
| Revisor no mesmo contexto do roteirista | Ele se ancora no raciocínio de quem escreveu, que é o ponto cego que o ADR 0004 tenta evitar |

## Consequências

Positivas:

- Busca na web, leitura de páginas e subagentes vêm prontos na rotina. O Python cuida só do que precisa ser determinístico: seleção e validação.
- Os prompts ficam versionados em `rotina/`, então mudar o comportamento do roteirista é um commit revisável.
- O portão do roteiro é código testado (`tests/test_roteiro.py`), e não uma promessa do prompt.
- O áudio só é gerado para roteiros aprovados, o que poupa a cota do Gemini.

Negativas:

- Roteirista e revisor continuam sendo o mesmo modelo. Sem contexto, o revisor perde o viés de quem escreveu, mas não as lacunas de conhecimento que os dois compartilham. Ele não tem acesso ao livro, então a regra de tratar como `imprecisa` uma atribuição que não dá para confirmar é a principal defesa.
- Se a rotina não rodar, ninguém fica sabendo, porque o Actions só reage a push. Falta um workflow agendado que abra uma issue quando passar mais de 36 horas sem commit em `episodios/`.
- O push direto na `main` é aceitável no MVP. Depois de validado, o fluxo pode passar por PR.
- A rotina consome o plano do Claude. O Lucas aceitou esse custo.

## Critério de revisão

Revisar se mais de 20% das execuções de um mês terminarem sem roteiro aprovado, ou se um erro grave aparecer no feedback de um episódio que o revisor aprovou.
