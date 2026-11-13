# Avaliação de HX do site

Investigação da issue #5. O ponto de partida é uma confusão recorrente: quem chega ao site não identifica de qual saga é o episódio. A etiqueta de sisal foi criada para resolver isso e não resolveu.

| Parte | Estado |
|---|---|
| 1. Avaliação heurística | Feita em 2026-11-13 |
| 2. Teste com pessoas | A fazer, depois que #6 e #7 estiverem no ar |

**Versão avaliada:** o site gerado com os episódios reais (sw-001, sw-002, sl-001, si-001) e com as mudanças da #6 (capa sem número) e da #7 (saga no título do feed) aplicadas, a 1280 px e a 390 px de largura.

## Parte 1: avaliação heurística

Uma passada pelas 10 heurísticas de Nielsen na página inicial e na página de episódios. Severidade: **alta** atrapalha a tarefa principal (saber o que ouvir e onde está); **média** atrapalha uma tarefa secundária ou quebra uma expectativa; **baixa** é atrito que não impede nada.

### Achados

| # | Achado | Heurística | Severidade | Issue |
|---|---|---|---|---|
| A1 | A cor da saga muda de uma seção para outra | Consistência e padrões | Alta | #10 |
| A2 | Nada explica por que o próximo episódio é de outra saga | Visibilidade do estado do sistema | Alta | #11 |
| M1 | O site promete um episódio por dia, mas o ritmo depende da validação | Correspondência com o mundo real | Média | #12 |
| M2 | O card da saga não leva aos episódios dela, e o filtro não fica na URL | Controle e liberdade | Média | #13 |
| B1 | A mesma saga tem dois nomes | Consistência e padrões | Baixa | |
| B2 | O estado do próximo episódio usa o vocabulário da pipeline | Correspondência com o mundo real | Baixa | |
| B3 | No celular, o episódio só aparece depois de uns 1.300 px de rolagem | Estética e design minimalista | Baixa | |
| B4 | Só dá para assinar por RSS, e o endereço aparece cortado | Correspondência com o mundo real | Baixa | |

**A1. A cor da saga muda de uma seção para outra.** Os cards de episódio e as etiquetas usam uma cor fixa por saga (`[data-saga]` em `site/estilo.css`). A seção "Sete sagas" pinta por posição (`.saga:nth-child(4n+…)`, quatro cores em rodízio para sete sagas), e a seção de vozes tem cor própria por pessoa. Soluções é verde no card e amarela na seção de sagas. A Helena, voz da saga Software, aparece azul, a cor de Sistemas. A cor é o sinal mais rápido de saga que o site tem, e hoje ele se contradiz.

**A2. Nada explica por que o próximo episódio é de outra saga.** A regra de publicação (sai todo episódio com referências validadas, de qualquer saga) não aparece no site. Na versão avaliada, "Pra ouvir agora" é Sistemas e "Próximo episódio" é Infraestrutura, lado a lado, sem transição. A seção "Como funciona" conta as etapas de produção, mas não a ordem em que os episódios saem. É a candidata mais forte a causa da confusão que abriu a #5, mais até que o número da capa.

**M1. O ritmo prometido não é o real.** O hero diz "Podcast diário de arquitetura" e "uma conversa de 15 a 20 minutos por dia". A abertura do sw-001 repete a promessa no áudio ("um episódio por dia"). Os quatro primeiros episódios saíram em 7, 9, 11 e 12 de novembro. Quem assina esperando um episódio por dia vê dias vazios.

**M2. Não dá para ir de uma saga aos episódios dela.** Os cards de saga mostram o progresso ("No ar · 2 de 4"), mas não são links. O filtro da página de episódios guarda o estado só na página: `site/app.js` lê apenas a âncora do episódio, então "episódios da saga Software" não tem endereço próprio.

**B1. A mesma saga tem dois nomes.** A etiqueta e o filtro dizem "Software", e a seção de vozes diz "Voz convidada da saga Arquitetura de Software".

**B2. O estado do próximo episódio usa o vocabulário da pipeline.** "Fontes conferidas. O roteiro é o próximo a ser escrito." descreve a esteira de produção, não responde o que o ouvinte quer saber: quando sai.

**B3. No celular, o conteúdo vem depois da ilustração.** A 390 px, a ilustração do hero empurra o episódio mais recente para uns 1.300 px de rolagem, e a etiqueta da saga só aparece ali.

**B4. A assinatura pede conhecer RSS.** O único caminho é copiar o endereço do feed, que aparece cortado no campo. Para quem está começando na área, o público-alvo, "app de podcast que aceite RSS" pode não dizer nada. Faz sentido enquanto o podcast não está no Spotify, mas é um achado para o teste confirmar.

## Parte 2: teste com pessoas

### Quem

Cinco participantes: pelo menos dois do público-alvo (dev em início de carreira) e nenhum que tenha ajudado a construir o site. Cinco pessoas bastam para achar a maior parte dos problemas de uso, não para medir com significância.

### Como

- Sessão moderada de até 15 minutos, presencial ou por chamada com tela compartilhada, com a pessoa pensando em voz alta.
- Celular de preferência, porque é onde podcast se ouve.
- Quem modera não explica nem defende o design. Se a pessoa travar, pergunte "o que você esperava encontrar?" e siga para a próxima tarefa.
- Anote o que a pessoa faz, não só o que ela diz.

### Roteiro do moderador

Abertura: "Vou te mostrar o site de um podcast. Não é teste de você, é do site: se algo for confuso, a culpa é dele. Pensa em voz alta enquanto usa."

| # | Tarefa | Sucesso quando | Mede |
|---|---|---|---|
| T1 | Mostre a página inicial por 5 segundos e esconda. "De que saga é o episódio mais recente e em que ponto dela ele está?" | Diz a saga e a posição certas | A etiqueta e a capa (#6) |
| T2 | Toque os 30 primeiros segundos de um episódio sem mostrar a tela. "De que saga é esse episódio?" | Diz a saga certa | A ligação entre áudio e site |
| T3 | "Você ouviu este episódio ontem" (mostre o título de um episódio que não é o mais recente). "Ache o próximo da mesma saga." | Chega ao episódio certo | A2, M2 |
| T4 | "Ache todos os episódios da saga Software." | Chega à lista filtrada | M2 |
| T5 | "Descubra qual é o desafio do episódio de hoje." | Lê o desafio | Hierarquia do card de destaque |
| T6 | "Assine o podcast no seu app." | Termina a assinatura ou diz por que não consegue | B4 |

Fechamento: "Com que frequência você acha que sai episódio novo?" (M1) e "Se fosse indicar um episódio para alguém, como você diria qual é?" (identificador).

### Resultados

| Tarefa | P1 | P2 | P3 | P4 | P5 | Sucesso |
|---|---|---|---|---|---|---|
| T1 | | | | | | /5 |
| T2 | | | | | | /5 |
| T3 | | | | | | /5 |
| T4 | | | | | | /5 |
| T5 | | | | | | /5 |
| T6 | | | | | | /5 |

Perfil dos participantes (sem nomes):

| | Perfil | Ouve podcast? | Dispositivo |
|---|---|---|---|
| P1 | | | |
| P2 | | | |
| P3 | | | |
| P4 | | | |
| P5 | | | |

Achados novos do teste entram na tabela da parte 1, com a evidência ("3 de 5 não acharam...").

## Identificador do episódio

A pergunta que a investigação precisa responder: que identificador funciona escrito no site e falado no áudio?

| Opção | No site | No áudio | Já existe hoje |
|---|---|---|---|
| Nome da saga + posição | "Saga Software · ep. 2" | "segundo episódio da saga Software" | Na etiqueta e no título do feed (#7) |
| Sigla + número | "SW·02" | "esse-dáblio zero dois" | Não |
| Número global | "#4" | "episódio quatro" | Não, e brigaria com a ordem por saga |
| Nenhum | Só o título | Só o tema | É o que o áudio faz hoje |

Hipótese de partida: **nome da saga + posição**. É o único que já se lê e se fala do mesmo jeito, e já está no site e no feed. A sigla não se fala. O número global não diz a saga. As respostas de T1, T2 e a pergunta de fechamento confirmam ou derrubam a hipótese.

Um detalhe que pesa para a T2: a abertura do episódio (`rotina/roteirista.md`) só pede o tema do dia. Na prática, o áudio cita a saga quando abre uma nova (sw-001, sl-001, si-001) e não cita quando continua uma (sw-002), que é justamente quando o ouvinte mais precisa saber onde está. Se a T2 falhar, o conserto provável é a abertura dizer a saga e a posição, e isso vira issue da rotina, não do site.

## Recomendação

Ficará aqui depois da parte 2: o identificador escolhido, com a evidência, e a ordem de ataque dos achados.
