# Pebamotion

Trailers animados dos episódios, para as redes e para quem ainda não ouve o Pebacast. A linguagem é a página de cordel do site em movimento: mesma paleta, mesmas fontes, o mesmo peba. Só a cor e a paisagem da saga mudam de um episódio para outro. Decisão e alternativas no [ADR 0010](../docs/adr/0010-pebamotion.md).

```
pebamotion/
  palco.html              página que o renderizador abre (?ep=da-001&f=vertical)
  motor/pebamotion.js     motor: tokens, sagas, formatos e as primitivas da linguagem
  motor/palco.js          carrega fontes e paisagens do site, a linha do tempo e as cenas
  episodios/<ep>/
    episodio.json         recortes de voz, trilha, variantes e limites de render
    linha.json            gerado: onde cada recorte e cada palavra caem no trailer
    cenas.js              as cenas do episódio
scripts/pebamotion.py     CLI (transcrever, sugerir-cortes, linha, quadros, produzir)
```

## Regras

1. **Toda palavra grande na tela foi dita no áudio.** Rótulos de diagrama podem vir do episódio; a tipografia cinética só cita a fala.
2. **Voz é recorte literal do roteiro, cortado em silêncio.** `tests/test_pebamotion.py` confere cada recorte contra o `roteiro.json`.
3. **Apresentador no papel cru, convidada na cor da saga**, como no site.
4. **No 9:16, o terço de baixo fica livre** para a interface do Reels, TikTok e Shorts.
5. **Identidade com fonte única.** Fontes vêm de `site/fontes/`, paisagens das `--cena-*` de `site/estilo.css`. Não copie nada do site para cá.
6. **Cada quadro é função pura do tempo.** Nada de estado entre quadros: qualquer instante renderiza igual.

## Vocabulário (primitivas em `PM`)

| Primitiva | Uso |
|---|---|
| `carimbo` | palavra que cai como prensa (escala 1,55 → 1 em 0,22 s) |
| `blocoDeTipo` | empilha carimbos na zona de tipografia, ajustando à largura |
| `tinta()` | contorno que "ferve" a 8 fps, textura de xilogravura |
| `folheto` | ficha com borda grossa e sombra amarela deslocada |
| `barbante`, `pregador` | varal, arestas de grafo, puxões |
| `no`, `cilindro`, `inseto`, `peba` | nó de grafo, banco, bug, tatu-peba |
| `etiqueta` | etiqueta da saga amarrada com sisal |
| `legenda` | legenda karaokê com o chip de quem fala |
| `tremida` | tremida curta de câmera depois de um carimbo pesado |
| `caminho` | mede um path SVG: ponto, direção e o lado do casco de quem anda nele |
| `pendulo`, `mola`, `E.*` | curvas de movimento |

O som também é parte da linguagem: as cenas declaram eventos (`eventosSonoros()`), e cada tipo (`carimbo`, `prensa`, `papel`, `sisal`, `pregador`, `corte`, `puxao`, `cava`...) é sintetizado em `scripts/pebamotion.py`.

## Preparar

```sh
pip install -e ".[motion]"
python -m playwright install chromium   # ou CHROME=<caminho do Chrome>
```

Precisa do `ffmpeg` no PATH e da faixa inteira em `assets/vinheta.mp3` ([docs/vinheta.md](../docs/vinheta.md)). O áudio do episódio é baixado do Release na primeira vez.

## Novo episódio

1. **Transcrever:** `python scripts/pebamotion.py transcrever <ep>` grava o tempo de cada palavra em `pebamotion/.cache/<ep>/palavras.json`.
2. **Escolher a fala:** crie `episodios/<ep>/episodio.json` (copie o do `da-001`). Cada recorte tem `id`, `persona`, `entrada`, `saida` (segundos no MP3 publicado), `respiro` (pausa antes dele no trailer) e `texto` (o trecho exato do `roteiro.json`). `python scripts/pebamotion.py sugerir-cortes <ep>` aproxima entrada e saída do silêncio mais próximo.
3. **Linha do tempo:** `python scripts/pebamotion.py linha <ep>` gera o `linha.json`.
4. **Cenas:** copie `episodios/da-001/cenas.js`, troque `EPISODIO.saga` (por exemplo `PM.SAGAS.seguranca`) e reescreva as cenas. `P(id, i)` é o instante da i-ésima palavra de um recorte: é assim que a animação fica presa à fala.
5. **Revisar quadros:** `python scripts/pebamotion.py quadros <ep> -t 3.2 10.5 [--formato horizontal] [--param nomes=0] [--so-fim]`.
6. **Produzir:** `python scripts/pebamotion.py produzir <ep>` grava em `pebamotion/saida/<ep>/` o trailer 9:16 e 16:9 com trilha, sem trilha e em cada variante, e o encerramento isolado. Os trechos já renderizados ficam em `.cache` e são reaproveitados; `--refazer` descarta.

## Trilha no DA 001

O trecho da introdução entra de forma que a banda chegue junto com o caso das clínicas (3,08 s da faixa no início do trailer), corta seco no painel preto de "O bug não liga pro banco" e volta no puxão do pregador a partir de 86,35 s, para a batida final da faixa (90,9 s) cair no carimbo "Pebacast". A voz abaixa a trilha (ducking de 60%), e o vídeo sai em −14 LUFS e −1,5 dBTP.
