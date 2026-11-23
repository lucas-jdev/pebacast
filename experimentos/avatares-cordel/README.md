# Avatares em xilogravura

Retratos das personas (`curriculum/personas/*.yaml`) no estilo cordel do site. Cada versão guarda o gerador e o resultado, para comparar as rodadas.

| Versão | Ideia | Por que mudou |
|---|---|---|
| `v1` | Traço preto sobre o papel da saga, sol serrilhado e faixa com o nome | Parecia ícone vetorial com moldura de cordel, e a cor da saga pintava o rosto, apagando o tom de pele |
| `v2` | Preto domina, figura talhada em branco, cor da saga só na nuvem de ondas, um objeto de cena por persona | Todos tinham o mesmo rosto, e acessórios viraram estereótipo (Helena, Otávio, Yasmin) |
| `v3` | Formato de rosto, nariz, boca e ombros por persona, objetos trocados, recorte redondo próprio para tamanhos pequenos | Versão usada no site; a Beatriz segue o desenho da v2 por escolha do Lucas |

O site usa dois recortes da v3, copiados para `site/avatares/`:

- `cartao/`: retrato sem moldura, no card de cada voz em "Quem conversa";
- `cabeca/`: só o rosto, com traço mais grosso, ao lado do nome na transcrição.

O tom de pele é feito pela técnica de gravura (rosto em papel, pontilhado ou em preto com traços em branco) e ainda não foi validado com pessoas de fora do projeto.

## Gerar de novo

Precisa de `rsvg-convert`, ImageMagick (`montage`, `convert`) e `fonttools` com `brotli`.

```sh
python experimentos/avatares-cordel/v3/gerar.py
cp experimentos/avatares-cordel/v3/saida/cartao/*.svg site/avatares/cartao/
cp experimentos/avatares-cordel/v3/saida/cabeca/*.svg site/avatares/cabeca/
```
