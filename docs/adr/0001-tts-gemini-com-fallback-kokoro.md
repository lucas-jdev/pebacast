# 0001. Síntese de voz com Gemini TTS e fallback local em Kokoro

- Status: Aceito em 2026-11-07, após o [teste cego de vozes](../../experimentos/teste-vozes/README.md)
- Data: 2026-11-05
- Revisado: 2026-11-06, troca do modelo preview pela família Gemini 3.8

## Contexto

Cada episódio tem de 15 a 20 minutos, cerca de 15 a 20 mil caracteres. Com um episódio por dia, a demanda é de 450 a 600 mil caracteres por mês.

O podcast terá até oito personas (apresentador e sete experts), cada uma com voz e temperamento próprios. Por isso, os critérios que mais pesam são:

1. quantidade de vozes distintas em pt-BR;
2. controle de emoção e estilo por persona;
3. custo zero sem cartão de crédito cadastrado;
4. viabilidade no runner gratuito do GitHub Actions.

Em 23/09/2026, o Google lançou o `gemini-3.8-flash-tts` e o `gemini-3.8-flash-lite-tts`, os dois disponíveis no free tier. O Flash-Lite foi apresentado como substituto direto do `gemini-3.1-flash-tts-preview`, que era o candidato da primeira versão deste ADR.

## Decisão

Usar o `gemini-3.8-flash-tts` como provedor principal e o Kokoro 82M, rodando localmente no runner, como fallback. Os dois ficam atrás da interface `TtsProvider`. O modelo é parâmetro de configuração, então trocar para o Flash-Lite custa uma linha.

A integração usa a API `interactions` do SDK `google-genai`, que aceita um estilo diferente para cada fala (`speech_metadata.style`). Assim a mesma persona pode variar de emoção ao longo do episódio sem trocar de voz.

## Alternativas consideradas

| Opção | Vozes | Controle de estilo | Situação |
|---|---|---|---|
| Gemini 3.8 Flash TTS | 30 | Por fala, em linguagem natural | Escolhida. No máximo 2 falantes por requisição |
| Gemini 3.8 Flash-Lite TTS | 30 | Por fala, em linguagem natural | Concorre no teste cego. Mais barato se um dia sair do free tier |
| Google Cloud Chirp 3 HD | Muitas | Ritmo e pausa | Exige billing ativo e cobra automaticamente acima de 1 milhão de caracteres/mês |
| Kokoro 82M | 3 em pt-BR | Nenhum | Fallback. Não comporta 8 personas |
| Piper | 4 em pt-BR, todas masculinas | Nenhum | Concorre no teste como referência. Não tem voz feminina em pt-BR |
| Chatterbox Multilingual | Clonagem | Sim | Precisa de GPU com 8 a 16 GB, inviável no runner gratuito |

## Consequências

Positivas:

- As personas ganham identidade sonora e emoção por fala.
- O limite de dois falantes por requisição se encaixa no formato apresentador + expert. Os falantes são agrupados em blocos de até dois automaticamente.
- A interface `TtsProvider` permite trocar de provedor sem alterar o resto da pipeline.

Negativas:

- Os limites do free tier ficam no painel do AI Studio, por projeto, e não em tabela pública. Podem mudar sem aviso.
- Os preços pagos da família 3.8 dobram em 01/01/2027. Não afeta o free tier, mas afeta o plano B.
- No fallback, o episódio sai sem emoção e com só 3 vozes. É aceitável como degradação temporária, não como estado permanente.
- O Kokoro exige Python abaixo de 3.13. Ver [ADR 0005](0005-python-312-na-pipeline.md).
- No free tier, o conteúdo enviado pode ser usado pelo Google para melhorar seus produtos. Aceitável, porque o conteúdo é público por natureza.

## Critério para aceitar

O teste cego compara os quatro candidatos com o mesmo trecho de 2 minutos, notas de 1 a 5 em naturalidade, pronúncia de termos técnicos em inglês e diferenciação entre as personas. O Gemini é aceito se vencer em naturalidade e em diferenciação. Entre os dois modelos Gemini, a pronúncia técnica desempata.

### Resultado do teste (2026-11-07)

As notas foram dadas de 1 a 10, e não de 1 a 5 como previa a ficha. Isso não muda a comparação, que só depende da ordem das notas.

| Candidato | Amostra | Naturalidade | Pronúncia técnica | Diferenciação | Média |
|---|---|---|---|---|---|
| `gemini-3.8-flash-tts` | D | 9 | 10 | 10 | 9,67 |
| `gemini-3.8-flash-lite-tts` | A | 8 | 9 | 10 | 9,00 |
| Kokoro | B | 4 | 6 | 10 | 6,67 |
| Piper | C | 5 | 8 | 5 | 6,00 |

O `gemini-3.8-flash-tts` venceu sozinho em naturalidade e empatou no topo em diferenciação com o Flash-Lite e o Kokoro. Contra o Flash-Lite, a pronúncia técnica desempata a favor do Flash (10 contra 9). A decisão fica como estava: Flash como principal, Kokoro como fallback.

Observações da escuta que valem acompanhar nos episódios:

- Os dois modelos Gemini "engasgam" em alguns momentos. No Flash-Lite, a voz do Davi também perde a naturalidade num trecho.
- O Kokoro soa robótico, principalmente na voz do Davi, e erra parte dos termos técnicos. Isso confirma que ele só serve como degradação temporária.

## Critério de revisão

Revisar esta decisão se o Gemini TTS sair do free tier, se o fallback for usado em mais de 3 episódios num mesmo mês ou se surgir modelo aberto com mais de 5 vozes pt-BR que rode em CPU.

## Fontes

- [Speech generation, documentação da Gemini API](https://ai.google.dev/gemini-api/docs/speech-generation?hl=de)
- [Gemini 3.8 Flash TTS e Flash-Lite TTS: preços (Neomanex)](https://neomanex.com/news/gemini-3-8-flash-tts-flash-lite-tts-api-pricing)
- [Is Gemini 3.8 TTS free? (Projedefteri)](https://projedefteri.com/en/blog/is-gemini-3-8-tts-free/)
- [Google Cloud Text-to-Speech pricing](https://cloud.google.com/text-to-speech/pricing/?authuser=7)
- [Lista de vozes do Piper](https://github.com/rhasspy/piper/blob/master/VOICES.md)
- [Best Open-Source TTS 2026 (ocdevel)](https://ocdevel.com/blog/20250720-tts)
- [Rápido TTS, benchmark pt-BR (Hugging Face)](https://huggingface.co/edwixx/rapido-tts)
