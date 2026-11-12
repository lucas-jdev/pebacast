# Pebacast

O Pebacast é um podcast gerado automaticamente para estudo de arquitetura em sete sagas: Software, Soluções, Sistemas, Dados e Informação, Infraestrutura, Segurança e Corporativa.

Cada episódio tem entre 15 e 20 minutos, é um diálogo entre o apresentador e o expert da saga e termina com um desafio prático.

## Status

MVP privado: uma saga (Software), quatro episódios, um expert. O feed é consumido no AntennaPod como homologação, seguindo os critérios do Spotify. A publicação no Spotify depende do critério de go/no-go descrito no fim de [docs/pipeline.md](docs/pipeline.md).

## Como funciona

1. Seleciona o próximo episódio pendente com referências verificadas, de qualquer saga, começando pela publicada há mais tempo e respeitando pré-requisitos.
2. Busca notícias relacionadas em cascata (7 dias, 30 dias, 60 dias) ou cria um cenário hipotético.
3. O roteirista (Claude Opus 5.5, numa rotina agendada) gera o diálogo em JSON a partir da especificação do episódio e das personas.
4. Um subagente revisor, sem o contexto do roteirista, verifica cada afirmação contra as referências curadas e aponta correções.
5. O roteirista aplica as correções. Se o roteiro não for aprovado em dois ciclos, o episódio não é publicado.
6. A rotina commita o episódio. O GitHub Actions valida o roteiro de novo, sintetiza o áudio, monta e publica no feed.

Detalhes em [docs/pipeline.md](docs/pipeline.md).

## Estrutura

```
src/podcast/                  código da pipeline (Python 3.12)
src/podcast/tts/              interface TtsProvider e adaptadores Gemini, Kokoro e Piper
src/podcast/roteiro.py        seleção, contexto e validação usados pela rotina do roteirista
rotina/                       instruções da rotina do roteirista e do revisor
episodios/<id>/               notícia, roteiro, revisões e publicação de cada episódio
experimentos/teste-vozes/     teste cego de vozes do ADR 0001
site/                         CSS, JS e ícone da página do Pages (o HTML sai de src/podcast/site.py)
tests/                        testes automatizados
config/pipeline.yaml          parâmetros da pipeline
curriculum/sagas/             especificação das sagas e episódios (curadoria manual)
curriculum/personas/          bíblia das personas
feedback/<saga>/              avaliações pessoais por episódio
docs/fronteiras-das-sagas.md  o que pertence a cada saga
docs/pipeline.md              etapas da geração
docs/adr/                     decisões de arquitetura
```

## Desenvolvimento

```bash
uv venv --python 3.12
uv pip install -e ".[gemini]" pytest
pytest
```

Os testes usam provedores falsos e não chamam nenhuma API. Só o teste de exportação de MP3 exige ffmpeg no PATH.

## Curadoria

Todo episódio aponta livro e capítulo em `referencias`. O campo `referencias_verificadas` só vira `true` depois de conferir os capítulos no livro ou, sem acesso a ele, em pelo menos duas fontes secundárias independentes que concordem entre si. Nesse caso, um comentário no YAML registra o que foi conferido e onde. Com `exigir_referencias_verificadas: true` em `config/pipeline.yaml`, episódios não verificados não são gerados.

## Feedback

Depois de ouvir, copie `feedback/_template.yaml` para `feedback/<saga>/<id-do-episodio>.yaml` e preencha. A pipeline lê os feedbacks recentes da saga ao gerar os próximos episódios e nunca altera esses arquivos.

Campos:

- `nota`: de 1 a 5.
- `erros_encontrados[].gravidade`: `leve` (imprecisão que não muda o entendimento) ou `grave` (conceito errado). Erros graves contam para o critério de go/no-go.
- `desafio.link_artefato`: onde ficou o que você produziu no desafio (ADR, diagrama, anotação).

## Licença

O código está sob a licença [MIT](LICENSE). O conteúdo (episódios, roteiros, currículo, personas e documentação) está sob [CC BY 4.0](LICENSE-CONTENT.md).
