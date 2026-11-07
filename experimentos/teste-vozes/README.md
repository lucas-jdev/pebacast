# Teste cego de vozes

Valida o [ADR 0001](../../docs/adr/0001-tts-gemini-com-fallback-kokoro.md). Os quatro candidatos sintetizam o mesmo trecho de 2 minutos do episódio sw-001. As amostras saem anônimas (A, B, C, D), em ordem sorteada, no formato de produção (MP3 mono a 64 kbps) e com o volume normalizado. Sem a normalização, o candidato mais alto tende a parecer o melhor, e o teste deixa de ser cego.

| Candidato | O que é |
|---|---|
| `gemini-3.8-flash-tts` | Gemini, modelo principal |
| `gemini-3.8-flash-lite-tts` | Gemini, versão mais barata |
| `kokoro` | Modelo aberto, roda local |
| `piper` | Modelo aberto, roda local |

## Pré-requisitos

- Python 3.12 (o Kokoro não suporta 3.13) e [uv](https://docs.astral.sh/uv/)
- ffmpeg no PATH
- Chave do Gemini, criada no [Google AI Studio](https://aistudio.google.com/apikey)
- Cerca de 2 GB livres: o Kokoro instala o PyTorch e baixa o modelo na primeira execução

## Passo a passo

Todos os comandos rodam na raiz do repositório.

```bash
uv venv --python 3.12
uv pip install -e ".[gemini,kokoro,piper]"

python -m piper.download_voices pt_BR-faber-medium pt_BR-cadu-medium \
  --download-dir experimentos/teste-vozes/vozes-piper

export GEMINI_API_KEY="sua-chave"
python -m podcast.teste_vozes gerar
```

Se o Kokoro reclamar de espeak no Linux, instale com `sudo apt install espeak-ng`.

Para testar sem algum candidato, passe a lista: `--candidatos kokoro piper`.

## Avaliação

1. Ouça as amostras em `experimentos/teste-vozes/saida/amostras/`, de preferência no celular e com fone, que é como você vai ouvir os episódios.
2. Não abra `saida/.gabarito.json`.
3. Preencha `saida/avaliacao.yaml` com notas de 1 a 5 para cada critério.
4. Rode `python -m podcast.teste_vozes revelar`.

O `revelar` só mostra o resultado quando todas as notas estão preenchidas e dentro da escala.

## Interpretação

O critério do ADR 0001: o Gemini é aceito se vencer em naturalidade e em diferenciação. A pronúncia técnica desempata.

Duas limitações conhecidas, que não são defeito do teste:

- **Piper:** não tem voz feminina em pt-BR (as vozes disponíveis são cadu, edresson, faber e jeff). A Helena sai com uma segunda voz masculina, e isso conta contra ele em diferenciação.
- **Kokoro e Piper:** ignoram o campo `estilo`. Só o Gemini interpreta emoção. Isso faz parte do que está sendo avaliado.

Depois do resultado, atualize o status do ADR 0001 e registre as notas nele.
