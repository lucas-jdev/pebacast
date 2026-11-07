# 0003. Agendamento com GitHub Actions e gatilho manual por saga

- Status: Substituído em parte pelo [ADR 0006](0006-roteiro-por-rotina-claude.md)
- Data: 2026-11-05
- Revisado: 2026-11-07. O agendamento noturno passou para a rotina do Claude. O workflow do Actions agora é disparado pelo push do roteiro em `episodios/`. O `workflow_dispatch` e a issue em caso de falha continuam valendo.

## Contexto

O episódio precisa estar pronto pela manhã. Gerar com muita antecedência deixa as notícias velhas, então a geração acontece na noite anterior. No futuro, o Lucas quer escolher manualmente a saga de um dia.

Dados conferidos em 2026-11-05.

## Decisão

Workflow do GitHub Actions com dois gatilhos:

- `schedule` com cron `17 5 * * *`, que é 05:17 UTC (02:17 em Brasília), num minuto quebrado para fugir do pico de execuções no início de cada hora;
- `workflow_dispatch` com o parâmetro opcional `saga`, que sobrescreve a agenda do dia.

Qualquer falha abre uma issue no repositório.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| Serviço externo chamando o `workflow_dispatch` | Execução pontual | Exige guardar um token do GitHub num terceiro. Risco de segurança desnecessário para um atraso tolerável |
| Cron no computador pessoal | Controle total | Depende da máquina ligada. Só compensaria com TTS local pesado |

## Consequências

Positivas:

- Custo zero: repositório público tem minutos ilimitados nos runners padrão.
- O gatilho manual por saga existe desde o primeiro dia, sem custo extra.
- O commit diário do feed mantém o repositório ativo, então o workflow não é desativado por inatividade.

Negativas:

- O cron pode atrasar ou ser pulado em horários de carga alta. A geração na madrugada absorve atrasos de horas.
- Se a pipeline quebrar e parar de commitar, o GitHub desativa o agendamento após 60 dias sem atividade em repositório público. A issue aberta em caso de falha é o que impede essa morte silenciosa.

## Critério de revisão

Revisar se mais de 2 execuções agendadas forem puladas num mesmo mês.

## Fontes

- [Disabling and enabling a workflow (GitHub Docs)](https://docs.github.com/enterprise-server@3.4/actions/managing-workflow-runs/disabling-and-enabling-a-workflow)
- [GitHub Actions Scheduled Workflows (cronuru)](https://cronuru.com/guides/github-actions-scheduled-workflows)
