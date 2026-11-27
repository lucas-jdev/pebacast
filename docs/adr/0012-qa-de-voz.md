# 0012. QA de voz pós-publicação

- Status: Aceito
- Data: 2026-11-27
- Complementa: [ADR 0008](0008-regravacao-em-dois-passos.md) (o QA de voz pode disparar o passo 1) e [ADR 0011](0011-cota-esgotada-espera.md) (o disparo respeita a cota)

## Contexto

O TTS às vezes erra a voz de duas formas que só se descobrem ouvindo:

- **Muda o timbre de uma persona no meio do episódio.** Cada bloco é uma chamada ao Gemini, e uma chamada pode sair com outra voz.
- **Deixa o Davi e a convidada parecidos demais.** No sw-002 original, as duas vozes se sobrepunham na faixa de 155 a 170 Hz. Esse áudio se perdeu na regravação.

O Lucas não ouve todo episódio inteiro antes de divulgar. Os QAs de áudio, texto e pronúncia não pegam nenhum dos dois casos.

O spike #27 (`docs/spikes/qa-de-voz.md`, no branch `spike/qa-de-voz`, que não é mergeado) provou uma abordagem com os 12 episódios Gemini publicados até então:

- 99,4 % dos turnos atribuídos à persona certa, e 30 de 30 fronteiras conferidas à mão;
- 7 de 7 defeitos sintéticos detectados no áudio, nenhum alarme nos 12 episódios bons e nenhum nos 2 controles;
- o job inteiro, com instalação, em 1 min 21 s a 1 min 38 s no `ubuntu-latest`.

## Decisão

**Separar quem fala pelo roteiro, sem modelo de fala.**

- As falas que foram ao TTS e a divisão em blocos de `agrupar_em_blocos` dão a persona, o bloco e o tamanho de cada turno.
- Um VAD de energia acha as pausas, e uma programação dinâmica escolhe onde cortar, com a duração de cada turno proporcional aos caracteres.
- Uma passada final soma a evidência de voz: quanto cada trecho entre pausas parece cada persona. Ela entrou porque o Gemini às vezes emenda dois turnos sem pausa, e aí a duração sozinha erra a fronteira e o erro se propaga (si-001 no spike).
- Só o miolo de cada turno é medido: sem 20 % de cada borda, com pelo menos 2 s, e sem o primeiro turno, que fica sob a vinheta.

**Medir o timbre com o WeSpeaker ResNet34-LM em ONNX, sem torch.**

- Arquivo `wespeaker_en_voxceleb_resnet34_LM.onnx`, da URL fixa do release `speaker-recongition-models` (com a grafia original) do `k2-fsa/sherpa-onnx`.
- SHA-256 `e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012`, conferido **antes** de carregar: o download vai para um arquivo temporário, e só vira `~/.cache/pebacast/modelos/<sha>.onnx` se o hash bater. No Actions, o cache (`actions/cache`) usa o SHA como chave.
- Extra `qa-voz`, com `onnxruntime==1.32.0` e `kaldi-native-fbank==1.23.3` em versões fixas (o numpy já é do núcleo). Os limites dependem do valor exato do embedding, então atualizar uma das duas é PR com os episódios medidos de novo.
- O F0 (YIN, em numpy) entra só no laudo, para explicar: "Davi em 136 Hz, Rafael em 107 Hz".

**Regras**, com os limites em `qa_voz.limites` no `config/pipeline.yaml`:

| Regra | Limite inicial | Nos 12 bons (spike) |
|---|---|---|
| Persona num bloco × resto do episódio | ≥ 0,75 | mín. 0,80 |
| Persona num bloco × impressão de voz de referência | ≥ 0,73 | mín. 0,78 |
| Persona no episódio inteiro × referência | ≥ 0,92 | mín. 0,97 |
| Cada par de personas do episódio | ≤ 0,61 | máx. 0,51 (a mesma voz: 0,96 ou mais) |
| Trechos medidos no bloco (e no resto) para julgar o bloco | ≥ 2 | |

Um bloco com menos trechos que o mínimo não é julgado, e o laudo diz isso. Não é reprovação: com um trecho só, o centróide do bloco é o próprio trecho, e uma frase curta ou emocionada viraria alarme falso. Nos 18 episódios publicados até 27/11, todos os blocos tiveram trechos suficientes.

**Roda dentro da pipeline, como os outros QAs.**

- `QaDeVoz.rodar` é chamado em `publicar_pendentes` dentro de `_rodar_qa_sem_segurar`, e também na regravação (`regravacao.py`).
- Uma falha do QA, como download falho, SHA errado ou modelo quebrado, vira "QA de voz não rodou" no resumo e nunca segura a publicação.
- O laudo vai para o resumo da execução ("Voz do &lt;id&gt;").

**Não roda no fallback.** No Kokoro, as personas dividem vozes. O laudo diz "não aplicável", e nada é aberto nem fechado (#28).

**Impressão de voz de referência versionada.**

- Fica em `config/vozes-referencia.json`. Por persona, guarda o vetor (256 números), a voz do Gemini, os episódios usados e a data. No topo, o SHA-256 do modelo.
- **Só muda por PR.** O comando `python -m podcast.qualidade_voz referencia --repo … --episodios …` mede os MP3 dos releases e reescreve o arquivo. O workflow **Referência de voz** (`workflow_dispatch`) roda o comando e abre um PR, nunca um push no `main`.
- Quando atualizar: na estreia de uma persona, depois que o Lucas ouvir o episódio; e no fim da fase aviso, só com os episódios marcados como bons.
- **Invalidação:** se o SHA do arquivo não for o da config, ou se a voz do Gemini da persona mudou no YAML dela, a referência daquela persona é ignorada. O laudo diz "sem referência válida", e as medidas de dentro do episódio continuam valendo.
- **Estreia:** uma persona sem referência só tem as medidas de dentro do episódio, e o laudo diz "sem referência". Um episódio anterior basta para a referência valer.
- O arquivo inicial foi gerado com os 12 episódios validados no spike. Os publicados depois entram quando o Lucas decidir.

**Incidente no padrão do QA do áudio.**

- Uma issue `incidente` por episódio, com o título "Voz do &lt;id&gt; fora do padrão". O título não termina em ": &lt;id&gt;", para o `publicar.yml` não fechá-la como roteiro reprovado.
- Reprovar de novo só comenta, e a issue fecha sozinha quando a voz do episódio passa.
- Na regravação:
  - a candidata é medida, o laudo vai para o resumo e para o release (`pebacast-<id>-candidata.voz.json`), e a issue aberta ganha um comentário: "aprovada: ouça e substitua" ou "também reprovou; a próxima regravação é manual";
  - o substituir lê esse laudo, sem medir de novo: se passou, fecha a issue; se não, comenta.

**Modos** (`qa_voz.modo`):

- **`aviso`** é o padrão, por uns 10 episódios Gemini: só abre a issue, e o Lucas marca em cada uma se o aviso acertou ou foi alarme falso.
- **`regravar`**: o Lucas liga, olhando a taxa de alarmes falsos da fase aviso. Com a voz reprovada na publicação, o `publicar.yml` dispara o `regravar.yml` (`acao=regravar`) depois do push e comenta na issue. Para isso, o job `publicar` tem `actions: write`.
- **No máximo uma candidata automática por episódio, garantida pela estrutura e sem marcador:** um episódio é publicado uma vez só (`episodios_pendentes` ignora quem tem `publicacao.json`), e o regravar e o substituir nunca disparam regravação. A segunda tentativa é sempre manual.
- **Cota (ADR 0011):** o disparo só acontece se a execução não deixou nenhum episódio aguardando a cota e se publicou um episódio só. Isso dá no máximo um disparo por execução: a publicação gasta de 4 a 5 requisições e a candidata outras 4 a 5, de 10 por dia. Se a regravação ainda assim encontrar a cota esgotada, ela falha sem fallback (ADR 0008) e comenta na issue que é preciso rodar à mão depois das 08:15 UTC.

## Atribuição do modelo

O QA de voz usa o modelo **WeSpeaker ResNet34-LM** (`wespeaker_en_voxceleb_resnet34_LM.onnx`):

- **Autoria:** projeto WeSpeaker (https://github.com/wenet-e2e/wespeaker), treinado no VoxCeleb.
- **Licença:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). O código do WeSpeaker é Apache-2.0, e os pesos seguem a licença do VoxCeleb, como diz o `docs/pretrained.md` do WeSpeaker.
- **Origem do arquivo:** exportação em ONNX publicada pelo `k2-fsa/sherpa-onnx` (release `speaker-recongition-models`), usada **sem modificações**.

O modelo é baixado na CI e não é redistribuído pelo pebacast.

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Diarização (pyannote e afins) | Traz o torch e um modelo de segmentação a mais, sem usar o que a pipeline já sabe: quem fala cada turno e em que ordem |
| Alinhamento forçado (transcrever e casar com o roteiro) | Era o plano B do spike e não foi necessário: a segmentação pelo roteiro acertou 99,4 %. Custaria um modelo de fala e minutos de CPU por episódio |
| Um falante por chamada ao TTS | Resolveria a separação na origem, mas dobra as requisições numa cota de 10 por dia e tira o contexto que segura as vozes do Gemini |
| CAM++ (3D-Speaker), Apache-2.0 | Funciona, com menos folga: 0,59 e 0,97 contra 0,51 e 0,96 do WeSpeaker na separação, e 97,3 % contra 98,1 % das trocas sintéticas. Fica como alternativa se a atribuição do CC BY incomodar, com os limites recalculados |
| Workflow separado (`qa-voz.yml`), proposta da interação 1 | Reinstalaria o ffmpeg e o Python, baixaria o MP3 de novo e duplicaria a orquestração que a pipeline já faz. As dependências são leves e o QA nunca segura a publicação |
| Referência que se alimenta sozinha a cada episódio aprovado | "Passou no QA" não é o mesmo que "soa certo": uma deriva lenta viraria o novo normal, e envenenaria justo o detector de deriva |
| Referência calculada na hora a partir dos releases | Uma dezena de downloads e de 30 a 47 s de análise por episódio publicado, crescendo com o catálogo, e sem curadoria |

## Consequências

Positivas:

- A troca de timbre e as vozes confundíveis aparecem numa issue no dia da publicação, com o bloco e a medida.
- Os quatro QAs seguem o mesmo padrão: laudo no resumo, uma issue por episódio e nada segurando a publicação.
- A referência é um arquivo revisável: dá para ver no diff que episódios entraram.

Negativas e limitações conhecidas:

- **Vozes femininas próximas.** Uma troca da Helena pela Camila num bloco foi detectada por pouco (0,73 contra o limite de 0,75), e nos embeddings 13 de 694 trocas sintéticas (1,9 %) escaparam, todas entre vozes femininas. A Camila e a Helena nunca estão no mesmo episódio. Se a fase aviso mostrar um caso que escapou, o ajuste é de configuração (limites por persona), não de arquitetura. O F0 não resolve, porque as faixas dessas vozes se sobrepõem.
- **Estreia com a voz inteira errada passa.** Ainda não há referência, então quem pega é o Lucas, ao ouvir a estreia antes de incluí-la na referência.
- **Dependência de um release de terceiro.** Se a URL do sherpa-onnx sumir, o QA "não roda" e nada é segurado. O CC BY 4.0 permite um espelho num release do próprio repositório, com o mesmo SHA (fora desta decisão).
- **O modelo roda no runner que tem o segredo do Gemini e escrita no repositório.** O SHA-256 conferido antes de carregar é o controle principal, e o ONNX não executa código. O `actions: write` serve só para disparar o `regravar.yml`, com um id que passou pela validação do formato.
- O job de publicar fica mais longo. Em 5 runs no `ubuntu-latest` (27/11, si-003, 16 min), o extra e o cache somaram de 3 a 6 s, e a análise de 21 a 61 s, conforme o runner: de 26 s a 67 s a mais por episódio, com mediana perto de 35 s.

## Quando revisar

- Ao trocar o modelo de TTS ou as vozes das personas: a referência é invalidada sozinha, mas os limites podem mudar.
- Ao mudar a vinheta ou a divisão em blocos.
- Ao trocar o modo de `aviso` para `regravar`, com a taxa de alarmes falsos da fase aviso.
- Ao sair do free tier (ADR 0011), porque a regra de cota do disparo perde o motivo.

Os dois ADRs com o número 0010 (`0010-pebamotion.md` e `0010-url-permanente-do-episodio.md`) são um assunto separado e ficam como estão.
