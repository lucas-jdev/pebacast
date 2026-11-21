# 0009. Prints de antes e depois automáticos nos PRs, com o artefato como fronteira de confiança

- Status: Aceito
- Data: 2026-11-15

## Contexto

O `CLAUDE.md` exige prints de antes e depois, no desktop e no celular, em todo PR que muda o visual do site. Até aqui era manual: rodar `scripts/prints.sh` no `main` e no branch, recortar, commitar no branch órfão `prints` e montar a tabela. Quem vem por fork pode não ter o Chrome, esquecer ou não ter permissão de escrita no branch `prints`. E o print da página inteira é grande demais para revisar.

Automatizar exige duas coisas que não combinam num job só: executar o código do PR (para gerar o site do branch) e escrever no repositório (branch `prints` e comentário no PR). Num PR de fork, o token do evento `pull_request` é só de leitura.

## Decisão

Dois workflows, separados por um artefato:

1. **Capturar prints** (`prints-capturar.yml`, evento `pull_request`, só quando o PR muda `site/**` ou `src/podcast/site.py`, permissão `contents: read`). Faz checkout do merge do PR e usa o primeiro pai dele como o `main` de comparação, gera os dois sites e, com o Playwright (Python, Chromium), fotografa cada seção separada de `index.html`, `episodios.html`, `sobre/` e de uma página de episódio (a primeira em ordem alfabética) a 1280 px e a 390 px. Compara os pares e sobe o artefato `prints` só com os que mudaram, mais o `manifesto.json` (número do PR e, por item, página, seção, tela e estado: `alterada`, `nova` ou `removida`).
2. **Comentar prints** (`prints-comentar.yml`, evento `workflow_run` ao fim do primeiro, com `contents: write` e `pull-requests: write`). Não faz checkout nem executa código do PR: usa só o `scripts/prints.py` do `main`. Baixa o artefato e valida tudo antes de escrever; confere que o PR existe e que a cabeça dele é o commit capturado; substitui a pasta `pr-<número>/` no branch `prints`; cria ou atualiza **um único** comentário, achado pelo marcador oculto `<!-- pebacast-prints -->`.

A lógica fica em `scripts/prints.py` (subcomandos `capturar`, `comparar`, `validar` e `comentario`), testada sem navegador em `tests/test_prints.py`. O `scripts/prints.sh` passa a usá-lo e continua gerando os prints localmente.

Regras:

- **Seções.** Cabeçalho é o `header` fora de `section` (`cabecalho`), rodapé é o `footer` fora de `section` (`rodape`), e cada `section` visível, inclusive aninhada, usa o `id`, senão o `aria-labelledby`, senão `secao-<posição>`. O nome é normalizado para `[a-z0-9-]`, e um nome repetido ganha `-2`, `-3`. Uma seção com o mesmo nome nos dois lados é comparada; só no PR é `nova` (o comentário mostra só "Depois"); só no `main` é `removida` (só "Antes"). Renomear o `id` de uma seção aparece como uma removida e uma nova.
- **Estabilidade do print.** Requisições fora do servidor local são bloqueadas (votos, GoatCounter), as animações ficam desligadas, e a página é rolada inteira antes de fotografar, para fontes, imagens e as cenas de fundo (máscaras CSS) estarem pintadas. Elementos fixos ou grudentos (o cabeçalho) ficam invisíveis no print das outras seções, para não cobrir o topo delas, e pseudo-elementos fixos (a textura de papel em `body::after`) ficam fora de todos os prints, porque cairiam num trecho diferente de cada seção conforme a rolagem. O recorte pega só os pixels inteiros dentro da seção: arredondar para fora traria uma linha da seção vizinha, e mudar a cor de uma seção marcaria a anterior também. O Chromium roda com `--disable-lcd-text`, `--font-render-hinting=none` e `--disable-font-subpixel-positioning`: o texto sai sempre em tons de cinza, porque o antialiasing subpixel liga ou desliga conforme a camada em que o texto é pintado, e no #72 o mesmo parágrafo saiu de um jeito em cada lado (#75).
- **Tolerância.** A seção conta como alterada quando o tamanho muda ou quando mais de **16** pixels diferem. Um pixel difere quando é liso nos dois lados (nenhum canal, RGBA de 0 a 255, varia mais de **6** entre ele e os 8 vizinhos) e algum canal varia mais de **8**, ou quando, em qualquer lugar, a média 3x3 da diferença passa de **48** em algum canal. Antes e depois são renderizados no mesmo runner, com o mesmo Chromium e as mesmas fontes, então a renderização é praticamente determinística: a tolerância só absorve ruído de antialiasing. Os números são pequenos para não esconder mudança real: trocar uma letra num texto mexe em dezenas de pixels, e mudar uma cor mexe em milhares.
- **Ruído na borda das letras (#75).** O antialiasing só redistribui a tinta entre vizinhos na borda das letras, que nunca é lisa, e a média 3x3 desfaz a redistribuição; até o #75 bastava um canal variar mais de 8, e o #72 marcou como alteradas seções idênticas (21.920 pixels em `index.html · inicio`; com a regra nova, 0). Uma palavra trocada e o fundo de um card trocado pelo tom vizinho da paleta continuam sendo pegos (testes em `tests/test_prints.py`, com um recorte das capturas do #72); passa o que é fino e de pouco contraste, como uma borda de 1 px.
- **Validação do artefato.** Só `manifesto.json` (até 64 KiB) e PNGs com nome no formato `<página>--<seção>--<tela>--<antes|depois>.png`, conferidos pela assinatura PNG e pelo cabeçalho `IHDR`, não pela extensão. Até 80 imagens, 8 MiB por imagem e 64 MiB no total. Nada de subpasta ou link simbólico. O manifesto tem exatamente `pr` (inteiro positivo) e `itens`, cada item com valores de listas fechadas e seção no padrão `[a-z0-9-]`, sem repetição, e as imagens presentes são exatamente as que o manifesto pede. Qualquer desvio recusa o artefato inteiro. Os dados do artefato chegam ao shell só por variável de ambiente, nunca interpolados no `run:`.
- **URLs.** As imagens ficam em `https://raw.githubusercontent.com/<repo>/prints/pr-<número>/<arquivo>.png`, com `?v=<commit>` no fim para o comentário atualizado não mostrar a imagem antiga do cache.
- **Versões fixas.** `playwright==1.63.0` e `pillow==12.3.0` no extra `prints` do `pyproject.toml`; actions nas versões maiores usadas no resto do repositório.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| `pull_request_target` num workflow só | Um arquivo, token de escrita também em fork | Executaria o código do fork (gerar o site roda Python do PR) com token de escrita |
| Um workflow `pull_request` com escrita | Simples | Em fork o token é só de leitura: quem mais precisa ficaria sem comentário |
| Print da página inteira | Nada a recortar | Grande demais para revisar, e qualquer mudança no topo desloca tudo e marca a página inteira como diferente |
| Comparar sem tolerância | Nenhum falso negativo | Ruído de antialiasing viraria falso "alterada" |
| Bloquear o merge por diferença visual | Regressão visual pega no CI | Fora do escopo: a mudança visual costuma ser o objetivo do PR |

## Consequências

Positivas:

- Quem contribui por fork, sem Chrome e sem acesso ao branch `prints`, recebe os prints no PR.
- O revisor vê só as seções que mudaram, uma a uma, no desktop e no celular.
- O comentário automático cumpre a regra dos prints do `CLAUDE.md`.

Negativas:

- O **Comentar** roda com a versão do `main` (é assim que o `workflow_run` funciona), então só passa a valer depois de mergeado: o PR que o introduz não recebe o comentário automático, e mudanças nele só são testáveis depois do merge.
- O branch `prints` cresce a cada push em PR visual. A pasta do PR é substituída, mas o histórico guarda as versões antigas.
- Outras páginas e o tema escuro ficam de fora; um PR que só mexe nelas recebe "Nenhuma mudança visual nas páginas capturadas".
- Um PR que muda a altura de uma seção desloca as seguintes por fração de pixel; o antialiasing do texto muda e elas também aparecem como alteradas, mesmo com o mesmo conteúdo. Falso "alterada" é preferível a esconder mudança real, e quem revisa vê que o par é igual.
- Um push rápido sobre outro pode descartar a captura antiga: o Comentar ignora o artefato se a cabeça do PR já mudou, e a captura mais nova comenta.
