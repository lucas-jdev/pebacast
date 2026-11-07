# Fronteiras das sagas

Cada saga responde a uma pergunta central. Um tópico pertence à saga cuja pergunta ele responde, não à saga onde ele aparece primeiro.

## As sete sagas

| Saga | Pergunta central | Escopo | Horizonte |
|---|---|---|---|
| Software | Como um sistema é organizado por dentro e por quê? | Uma aplicação ou um conjunto pequeno de serviços | Meses |
| Soluções | Quais peças resolvem este problema de negócio e como elas se conectam? | Uma iniciativa, ponta a ponta | Duração do projeto |
| Sistemas | Como as partes se comportam juntas, principalmente quando algo falha? | Sistemas distribuídos e integração hardware/software | Vida útil do sistema |
| Dados e Informação | Como a informação é modelada, governada e flui pela organização? | Ciclo de vida do dado | Anos |
| Infraestrutura | Onde e como tudo isso roda, com qual custo e confiabilidade? | Computação, rede, armazenamento, plataforma | Anos |
| Segurança | Quem pode fazer o quê, e o que acontece quando alguém tenta o que não deveria? | Transversal | Contínuo |
| Corporativa | Como a tecnologia sustenta a estratégia da organização? | A organização inteira | Anos |

## Conteúdo de cada saga

**Software.** Estilos arquiteturais, modularidade, características arquiteturais, padrões de design, ADRs, evolução e débito técnico.

**Soluções.** Levantamento de requisitos com o negócio, comprar versus construir, integração entre sistemas existentes, documento de solução, diagramas de contexto e de integração.

**Sistemas.** Consistência, consenso, replicação, particionamento, tolerância a falhas, concorrência, sistemas embarcados e IoT.

**Dados e Informação.** Modelagem, governança, qualidade, linhagem, pipelines, armazenamento analítico, data mesh e privacidade do dado.

**Infraestrutura.** Nuvem, redes, infraestrutura como código, contêineres e orquestração, observabilidade de plataforma, recuperação de desastres e FinOps.

**Segurança.** Modelagem de ameaças, identidade e acesso, criptografia aplicada, zero trust, segurança no ciclo de desenvolvimento e conformidade.

**Corporativa.** Mapa de capacidades de negócio, portfólio de aplicações, princípios de arquitetura, governança, roadmaps e frameworks como TOGAF.

## Tópicos disputados

| Tópico | Ângulo | Saga dona |
|---|---|---|
| Event-driven | Estilo arquitetural e organização do código | Software |
| Event-driven | Garantias de entrega, ordenação e idempotência | Sistemas |
| Event-driven | Broker gerenciado, capacidade e custo | Infraestrutura |
| Microsserviços | Decomposição e fronteiras de serviço | Software |
| Microsserviços | Falhas parciais, timeouts e retries entre serviços | Sistemas |
| Integração | Qual sistema conversa com qual para resolver o problema | Soluções |
| Integração | Padrões de integração dentro da aplicação | Software |
| Cache | Onde cachear dentro da aplicação | Software |
| Cache | Invalidação e consistência em cache distribuído | Sistemas |
| Observabilidade | Instrumentação do código | Software |
| Observabilidade | Plataforma de coleta, retenção e custo | Infraestrutura |
| Criptografia | Algoritmos, gestão de chaves e rotação | Segurança |
| Criptografia | Onde ela entra no fluxo da solução | Soluções |
| Banco de dados | Escolha do modelo de dados para a aplicação | Dados e Informação |
| Banco de dados | Replicação e particionamento | Sistemas |
| Banco de dados | Provisionamento, backup e alta disponibilidade | Infraestrutura |
| Domain-Driven Design | Modelagem tática e bounded contexts | Software |
| Domain-Driven Design | Mapa de capacidades e alinhamento com áreas de negócio | Corporativa |

## Regras

1. Um tópico tem uma única saga dona. Outras sagas citam o tópico só como referência, com o campo `ver` apontando para o episódio dono.
2. Quando o tópico tem mais de um ângulo, cada ângulo vira um episódio na saga dona daquele ângulo, e os episódios se referenciam.
3. Um tópico novo que não cabe em nenhuma linha da tabela é classificado pela pergunta central e depois adicionado à tabela.
