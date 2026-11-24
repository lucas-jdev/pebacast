# Teste cego de pronúncia

Compara variantes do dicionário de pronúncia (`tts.pronuncia` em `config/pipeline.yaml`) no Gemini. Cada variante narra as mesmas frases numa única requisição, para o teste caber na cota diária do free tier (10 requisições) ao lado do episódio do dia (4 a 5). As amostras saem anônimas (A, B, C), em ordem sorteada.

O primeiro experimento é o `pebacast.yaml`. No co-002, o Davi errou o "Pebacast" da abertura mesmo com a instrução que o teste de 2026-11-07 tinha escolhido. Aquele teste teve poucas amostras, e o Gemini não responde igual a cada vez.

## Rodar

No Actions, rode o workflow **Teste de pronúncia**. As amostras vão para um pré-release `teste-pronuncia-<execução>`, onde dá para ouvir no celular, e o gabarito vai para o artefato `gabarito` da execução.

Na sua máquina, com `GEMINI_API_KEY`:

```bash
python -m podcast.teste_pronuncia gerar
```

## Avaliar

1. Ouça as amostras sem abrir o gabarito.
2. Em cada amostra, conte quantas frases saíram com a pronúncia certa.
3. Revele com os acertos de cada amostra, na pasta onde está o `gabarito.json`:

```bash
python -m podcast.teste_pronuncia --saida <pasta> revelar A=4 B=1 C=3
```

A variante que acertar mais entra no `config/pipeline.yaml`, com a data do teste no comentário. Depois de revelar, apague o pré-release.

## Resultados

| Data | Experimento | Variante | Acertos |
|---|---|---|---|
| 2026-11-24 | `pebacast.yaml` | `instrucao` (a de produção) | 4 de 4 |
| 2026-11-24 | `pebacast.yaml` | `grafia` ("Péba-cast") | 4 de 4 |
| 2026-11-24 | `pebacast.yaml` | `grafia_e_instrucao` | 4 de 4 |

Empate: nenhuma variante foi melhor que a de produção, que ficou como estava. O erro do co-002 aconteceu numa fala de abertura longa, e este teste usa frases curtas. Se o QA de pronúncia (#107) voltar a pegar o "Pebacast" errado, o próximo teste deve usar a fala de abertura inteira.
