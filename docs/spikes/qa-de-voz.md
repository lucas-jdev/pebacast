# Spike: separação e medida de voz do QA de voz (#27)

Resultado do spike que prova a abordagem técnica da #21: separar quem fala guiando-se pelo roteiro e medir o timbre com um embedding de locutor em ONNX, sem torch. O código está no branch `spike/qa-de-voz` (`experimentos/qa-voz/`), que **não é mergeado**.

**Resumo:** a abordagem funciona e cabe no Actions.

| Critério | Meta | Resultado |
|---|---|---|
| Miolos atribuídos à persona certa | ≥ 90 % | **99,4 %** (492 de 495, 7 episódios); **30 de 30** fronteiras conferidas à mão |
| Separar as personas, estabilidade entre blocos, defeitos sintéticos | separar e detectar | separa em todos os 12 episódios; **0 de 12** episódios bons disparam; **7 de 7** defeitos no áudio detectados; **0 de 2** controles disparam |
| Instalação + análise de 17 min no `ubuntu-latest` | < 3 min | **1 min 21 s a 1 min 38 s** o job inteiro (análise: 29 a 47 s) |
| Limite diário do TTS no free tier | medir | **10 requisições/dia** do `gemini-3.8-flash-tts` (medido na #36; segue valendo) |

O plano B (alinhamento forçado) não foi necessário.

## Material

Os 12 episódios publicados com o Gemini que estão nos releases: `co-001`, `da-001`, `in-001`, `in-002`, `se-001`, `si-001`, `si-002`, `sl-001`, `sl-002`, `sw-001`, `sw-002` (o regravado; o original não existe mais) e `sw-003`. Todos têm a mesma vinheta (a fala começa em 7,5 s e o encerramento ocupa os últimos 11 s), então os turnos saem do roteiro e da config, sem metadado novo.

Nenhuma requisição ao Gemini foi gasta: os defeitos sintéticos usam fala real de outras vozes do Gemini, tirada de outros episódios publicados.

## 1. Separar quem fala

### Como

1. Os turnos (persona, caracteres e bloco) saem do mesmo código da publicação: `falas_do_episodio` (roteiro mais dicionário de pronúncia) e `agrupar_em_blocos`.
2. O VAD de energia (numpy, quadros de 10 ms) marca como pausa candidata todo trecho a mais de 35 dB abaixo do percentil 95, com pelo menos 120 ms.
3. Uma programação dinâmica escolhe K − 1 pausas para dividir a fala em K turnos. O custo de cada turno é o quadrado do log da razão entre a duração obtida e a esperada, que é proporcional aos caracteres mais uma folga de 12 por turno, porque fala curta demora mais que o proporcional. Pausas largas ganham um bônus pequeno. Uma segunda passada reestima a velocidade por bloco e por persona.
4. **Evidência de voz:** uma terceira passada soma quanto cada trecho entre pausas parece o Davi ou a convidada, pelos centróides da passada anterior (peso 0,1).
5. Mede-se só o **miolo** de cada turno: corta 20 % de cada borda, descarta turnos com miolo menor que 2 s e descarta o primeiro turno, que fica sob a vinheta.

O passo 4 não estava na proposta do Arquiteto. Ele entrou porque, só com a duração, o `si-001` desabou: o Gemini emendou a pergunta do Davi ("…tudo isso parece igual?") na resposta do Rafael ("Exatamente igual.") sem pausa nenhuma, e o erro de alinhamento se propagou por dezenas de turnos. Quando as duas vozes se parecem, a evidência de voz se anula e a segmentação volta a depender só da duração, sem esconder o defeito, porque os miolos misturados deixam os centróides ainda mais parecidos.

### Como foi conferido

- **Referência automática:** o Vosk (modelo pequeno de português) transcreve o episódio com o tempo de cada palavra, e um alinhamento de sequência casa essas palavras com as do roteiro. Ele casou de 81 % a 86 % das palavras. Um miolo está certo quando a maior parte dele cai em fala da persona certa. O Vosk serve só para conferir: não entra no QA.
- **À mão:** 30 fronteiras entre personas, 15 no `sw-002` (Helena e Davi) e 15 no `in-001` (Jorge e Davi, duas vozes masculinas), espalhadas pelo episódio. Para cada uma, conferi num espectrograma com o F0, as palavras ouvidas e o fim e o começo dos turnos pelo roteiro se a fronteira cai na pausa certa.
- **Calibração e validação separadas:** os parâmetros foram calibrados no `sw-002` e no `in-001`, e conferidos em `sl-002`, `da-001`, `co-001` e `si-002`. O `si-001` entrou depois, como o caso que motivou a evidência de voz.

### Números

| Episódio | Só duração | Com a evidência de voz | Erro mediano da fronteira | p90 |
|---|---|---|---|---|
| sw-002 (calibração) | 98,6 % | 98,6 % | 0,28 s | 0,99 s |
| in-001 (calibração) | 95,7 % | 100 % | 0,30 s | 0,98 s |
| sl-002 | 98,6 % | 100 % | 0,26 s | 0,98 s |
| da-001 | 94,3 % | 100 % | 0,26 s | 0,67 s |
| co-001 | 92,9 % | 98,6 % | 0,32 s | 0,81 s |
| si-002 | 93,4 % | 100 % | 0,34 s | 0,92 s |
| si-001 | 62,4 % | 98,8 % | 0,33 s | 1,45 s |
| **Total** | **89,9 %** (447/497) | **99,4 %** (492/495) | | |

**Conferência à mão:** com a evidência de voz, **30 de 30** fronteiras caem na pausa certa. Só com a duração, eram 25 de 30. As 5 erradas ficavam de 1 a 3 s fora, quando o turno começa com uma frase curta seguida de pausa ("Sempre tem.", "Exatamente isso.").

A margem do peso da voz é larga: de 0,05 a 1,0, o total fica entre 99,4 % e 100 %.

## 2. Medir o timbre

### Modelo

| | Escolhido | Alternativa |
|---|---|---|
| Modelo | WeSpeaker ResNet34-LM, VoxCeleb | 3D-Speaker CAM++, VoxCeleb |
| Arquivo | `wespeaker_en_voxceleb_resnet34_LM.onnx` | `3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx` |
| URL | release `speaker-recongition-models` do `k2-fsa/sherpa-onnx` | idem |
| SHA-256 | `e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012` | `98daf9bcf1c8abf3db374fec4c27a5eda7c58705bb3f180d057b085a72a88bb5` |
| Tamanho / saída | 25 MB / 256 dimensões | 28 MB / 512 dimensões |
| Licença | código Apache-2.0; **pesos CC BY 4.0** (seguem a licença do VoxCeleb, como diz o `docs/pretrained.md` do WeSpeaker). Permissiva, exige atribuição | Apache-2.0, como declara o 3D-Speaker |
| Distância entre Davi × convidada (máx. nos bons) e convidada trocada pelo Puck (mín.) | 0,51 e 0,96 (folga de 0,45) | 0,59 e 0,97 (folga de 0,38) |
| Timbre trocado num bloco, detectado (embeddings) | 98,1 % | 97,3 % |
| Análise no Actions (17,4 min) | 29 s | 18 s |

Escolho o **WeSpeaker ResNet34-LM**, porque separa com mais folga e detecta mais. Os 11 s a mais não pesam no tempo do Actions. O modelo é usado na CI e não é redistribuído, mas a atribuição do CC BY 4.0 vai no ADR da #21 e no `docs/pipeline.md`. Se o Lucas preferir uma licença sem exigência de atribuição, o CAM++ funciona com números um pouco piores e os limites recalculados.

As features vêm do `kaldi-native-fbank` (80 bandas, 16 kHz, sem dither, média subtraída por trecho). Para o WeSpeaker, as amostras vão na escala do int16. A inferência usa o `onnxruntime`, sem torch. Os pesos ficam fora do repositório: são baixados da URL fixa, conferidos pelo SHA-256 e guardados com `actions/cache`.

### Números (WeSpeaker, 12 episódios bons)

| Medida | Valor |
|---|---|
| Davi × convidada no mesmo episódio | de 0,27 a 0,51 (média 0,35) |
| Persona no bloco × resto do episódio | mín. 0,80, média 0,93, dp 0,03 (101 blocos) |
| Persona no bloco × impressão de voz de referência | mín. 0,78, média 0,94 (89 blocos) |
| Persona no episódio × impressão de voz de referência | mín. 0,97, média 0,98 |
| Mesma persona entre episódios | Davi mín. 0,95 (66 pares); Helena 0,96; Beatriz 0,98; Rafael 0,98; Jorge 0,98 |
| Miolo atribuído ao centróide certo, por vizinho mais próximo | 98,9 % |

A impressão de voz de referência de uma persona é a média dos centróides dela nos **outros** episódios (o episódio testado fica de fora). Camila, Yasmin e Otávio têm um episódio só, então a referência deles começa a valer a partir do segundo.

### Defeitos sintéticos

**No áudio**, com o pipeline inteiro (segmentação, embedding e regras): a fala de uma persona é trocada pela de outra voz do Gemini, tirada de outro episódio, mantendo o intervalo de cada turno. A emenda é feita a 24 kHz, a taxa do MP3 publicado, e o resultado é recodificado a 64 kbps. Os dois controles passam pelo mesmo caminho sem troca nenhuma.

| Caso | Disparou | Medida que pegou |
|---|---|---|
| Davi (Puck) trocado pelo Rafael (Charon) no bloco 2 do sw-002 | sim | bloco × episódio 0,49; × referência 0,51 |
| Davi trocado pelo Otávio (Iapetus) no bloco 1 do in-001 | sim | 0,44; 0,43 |
| Helena (Kore) trocada pela Camila (Erinome) no bloco 2 do sw-002 | sim, por pouco | 0,73 contra o limite de 0,75 |
| Jorge (Algenib) trocado pelo Rafael no bloco 1 do in-001 | sim | 0,53; 0,51 |
| Convidada inteira com a voz do Davi (Puck), sw-002 e in-001 | sim | Davi × convidada 0,98 |
| Helena inteira com a voz da Camila, sw-002 | sim | Helena × referência 0,77 (só a referência pega: por dentro, o episódio é coerente) |
| Controles (sw-002 e in-001 recodificados, sem troca) | **não** | |
| Os 12 episódios bons | **não** | |

**Nos embeddings**, em larga escala: em cada episódio, para cada persona e cada bloco com pelo menos 2 miolos, os miolos foram trocados pelos de cada outra voz, tirados de outro episódio. Foram detectados **681 de 694** casos (98,1 %). Todas as falhas são entre vozes femininas próximas (Camila 84 de 93, Helena 87 de 89, Yasmin 91 de 93). As vozes mais próximas entre si são Camila × Helena (0,78) e Camila × Yasmin (0,75). A convidada trocada pelo Puck foi detectada em 12 de 12 episódios.

**Par de vozes parecidas de propósito:** a voz mais próxima do Puck entre as personas é a do Otávio (Iapetus, 0,46). Com a convidada trocada por ela, nenhum dos 11 episódios dispara, e é o comportamento certo. Esse par já está no ar no `co-001` (0,48), ninguém reclamou, e ele fica abaixo do limite de 0,61. O limite marca vozes que soam como a mesma, não vozes do mesmo gênero.

### F0 (medida auxiliar)

| Persona (voz) | Mediana | p10–p90 |
|---|---|---|
| Davi (Puck) | 136 Hz | 117–160 |
| Otávio (Iapetus) | 125 Hz | 112–140 |
| Jorge (Algenib) | 113 Hz | 99–125 |
| Rafael (Charon) | 107 Hz | 95–117 |
| Helena (Kore) | 194 Hz | 163–216 |
| Yasmin (Laomedeia) | 204 Hz | 179–233 |
| Camila (Erinome) | 213 Hz | 198–233 |
| Beatriz (Sulafat) | 216 Hz | 198–239 |

O YIN em numpy roda em 2 a 4 s por episódio. Ele separa bem vozes de gêneros diferentes e serve para explicar a issue ("Davi em 136 Hz, Rafael em 107 Hz"). Entre vozes do mesmo gênero, as faixas se sobrepõem, então o F0 não decide sozinho. Ele também não reproduz a sobreposição de 155 a 170 Hz do sw-002 original, que se perdeu, como a #27 já previa.

## 3. Custo no Actions

Run real no `ubuntu-latest`, disparado por `workflow_dispatch` no branch do spike (`.github/workflows/spike-qa-voz.yml`), analisando o `sw-002` (17,4 min):

| Etapa | Sem o modelo em cache (`workflow_dispatch`) | Com o modelo em cache (`push`) |
|---|---|---|
| `checkout` e `setup-python` | ~11 s | ~4 s |
| ffmpeg (não vem no `ubuntu-latest`) | 39 s | 17 s |
| `pip install` (onnxruntime 1.32.0, kaldi-native-fbank 1.23.3, a pipeline) | 7 s | 6 s |
| Modelo (download de 25 MB e SHA-256, ou cache) | < 1 s | < 1 s |
| MP3 do release | 3 s | 1 s |
| Análise (decodificação, segmentação, embeddings, F0) | 29 s (0,9 + 20,2 + 6,5 + 1,8) | 47 s (0,7 + 33,5 + 11,1 + 1,6) |
| **Job inteiro** | **1 min 38 s** | **1 min 21 s** |

Runs: https://github.com/lucas-jdev/pebacast/actions/runs/44928240057 (`workflow_dispatch`) e https://github.com/lucas-jdev/pebacast/actions/runs/44930627821 (`push`). Com o mesmo código e o mesmo áudio, a análise variou de 29 s a 47 s entre runners. O pior caso medido (1 min 38 s) fica 1 min 22 s abaixo da meta.

A maior parcela é o ffmpeg. No `publicar.yml` ele já está instalado, então só custa de novo se o QA de voz rodar num job separado, como propõe o Arquiteto. A segmentação domina a análise porque calcula um embedding por trecho entre pausas (~500 por episódio).

## 4. Limite diário do TTS

**10 requisições por dia** do `gemini-3.8-flash-tts` no free tier. Foi medido na #36 (17/11), pelo `429 RESOURCE_EXHAUSTED` com `quotaId` `PerDay`, e é o mesmo número de `docs/pipeline.md`, do `docs/fluxo-do-episodio.md` e do ADR 0011. **Segue valendo** até onde dá para conferir sem gastar a cota:

- o modelo configurado ainda é o `gemini-3.8-flash-tts`;
- nenhum dos 12 runs mais recentes do `publicar.yml` registrou cota diária esgotada;
- não há issue "Cota do Gemini esgotada".

Remedir exigiria gastar 11 requisições, mais que a cota de um dia inteiro. Um episódio usa de 4 a 5, e uma regravação automática usa outras 4 a 5.

## 5. Proposta para `config/pipeline.yaml`

Limites iniciais, calculados nos 12 episódios bons: o menor valor visto com folga de 0,05, ou a média menos 3 desvios-padrão, o que for menor. Eles servem para a **fase aviso** da #21, e a calibração continua com o rótulo do Lucas em cada issue.

```yaml
qa_voz:
  modo: aviso                     # aviso | regravar (#21)
  modelo:
    url: https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx
    sha256: e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012
  segmentacao:
    folga_caracteres: 12          # turno curto demora mais que o proporcional
    peso_da_pausa: 0.2
    peso_da_voz: 0.1              # evidência de voz na segunda passada
    borda_do_miolo: 0.2
    miolo_min_s: 2.0
  limites:
    miolos_min_no_bloco: 2
    timbre_bloco_min: 0.75        # persona no bloco × resto do episódio (bons: mín. 0,80)
    timbre_referencia_min: 0.73   # persona no bloco × impressão de voz (bons: mín. 0,78)
    persona_referencia_min: 0.92  # persona no episódio × impressão de voz (bons: mín. 0,97)
    vozes_confundiveis_max: 0.61  # Davi × convidada (bons: máx. 0,51; voz igual: 0,96 ou mais)
```

## 6. Para a #21

- **Sem metadado novo para os episódios publicados:** a segmentação refaz os blocos com o roteiro e a config. O `pebacast-<id>-segmentos.json` sugerido pelo Arquiteto continua útil para episódios novos, caso a vinheta mude.
- **Impressão de voz de referência:** precisa de um arquivo versionado (por exemplo `config/vozes-referencia.json`, 256 floats por persona) e de uma regra para personas com um episódio só.
- **Ponto fraco conhecido:** uma troca num bloco entre vozes femininas próximas (Camila × Helena) passa raspando no limite, e nos embeddings 13 de 694 trocas escaparam. A fase aviso vai mostrar se isso acontece na prática.
- **Dependências do extra `qa-voz`:** `onnxruntime`, `kaldi-native-fbank` e `numpy`, sem torch. O ffmpeg já é usado pela pipeline.
- **ADR:** o QA de voz vira o **ADR 0012** (o 0009 são os prints, o 0010 o pebamotion e o 0011 a cota), na #21. Achado de passagem: o `main` tem dois ADRs com o número 0010 (`0010-pebamotion.md` e `0010-url-permanente-do-episodio.md`).

## Tempo do spike

Dentro do teto de 2 dias.
