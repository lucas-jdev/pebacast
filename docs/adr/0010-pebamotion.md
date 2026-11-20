# 0010. Pebamotion: trailers renderizados de SVG no navegador, com a identidade lida do site

- Status: Aceito
- Data: 2026-11-15

## Contexto

Para divulgar os episódios fora do app de podcast (colegas agora; Reels, TikTok e Shorts quando o podcast for para o Spotify), foi feito um trailer animado de 45 s do DA 001, em 9:16 e 16:9, com voz, trilha, efeitos e legenda. Ele precisa virar uma base reutilizável nas sete sagas, com a mesma identidade do site (cordel, sisal, peba, cor da saga), e ser reproduzível por quem tiver o repositório.

## Decisão

Um módulo `pebamotion/` com uma CLI em `scripts/pebamotion.py` (#32):

- **Desenho em SVG, em modo imediato, no Chromium headless.** Cada quadro é função pura do tempo (`window.desenhar(t)`); o Playwright fotografa quadro a quadro e o ffmpeg codifica (H.264, 30 fps, CRF 18), um MP4 por trecho, juntados com `concat`. Qualquer instante pode ser revisto sem rodar o vídeo (`quadros`).
- **A identidade vem do site, sem cópia.** Fontes de `site/fontes/` e paisagens das variáveis `--cena-*` de `site/estilo.css`, lidas pelo palco na hora. O grão de papel é gerado no navegador com semente fixa. A cor e a paisagem da saga vêm de `PM.SAGAS`, com as mesmas cores dos `[data-saga]` do site.
- **Voz literal.** Cada recorte é trecho do `roteiro.json`, cortado em silêncio no MP3 publicado; o tempo de cada palavra vem do faster-whisper, mas a legenda mostra o texto do roteiro. Um teste confere que todo recorte do `episodio.json` está no roteiro.
- **Som sintetizado e trilha nivelada pela voz.** Os efeitos (prensa, papel, sisal, pregador, a terra da toca) são gerados em código a partir dos eventos que as cenas declaram. A trilha é a faixa inteira de `assets/vinheta.mp3`, com ducking pela presença da voz, e o vídeo sai em −14 LUFS, −1,5 dBTP (padrão das redes; o episódio continua em −16).
- **Ferramenta local, fora da esteira.** O Lucas roda quando quer; nada muda no pipeline de publicação.

## Alternativas consideradas

| Opção | Vantagem | Por que não |
|---|---|---|
| Editor de vídeo (After Effects, DaVinci) | Ferramentas maduras de motion | Nada versionado nem reproduzível; cada saga recomeça à mão; não conversa com a esteira |
| Remotion (React) | Feito para vídeo programático | Traz Node, React e um bundler para o projeto, e licença comercial para empresas; o ganho sobre SVG puro é pequeno aqui |
| Lottie ou Rive | Leve, toca no navegador | Precisa de editor visual para criar; não lê o CSS do site |
| Canvas 2D | Mais rápido por quadro | Perde texto e filtros do SVG (o contorno de tinta) e não reaproveita o vocabulário do site |
| Gerar o trailer no GitHub Actions | Sem depender da máquina do Lucas | Cedo: as cenas ainda são escritas à mão por episódio (ideia #33) |

## Consequências

Positivas:

- Um episódio novo reaproveita motor, legenda, etiqueta, som e assinatura; o trabalho fica nas cenas e na escolha dos recortes.
- Mudar o site muda o trailer: fontes, paisagens e cores têm uma fonte só.
- A regra "toda fala é recorte literal" é verificada por teste.

Negativas:

- Render lento: cerca de 10 quadros por segundo, uns 2 min e meio por variante de 45 s. O `produzir` reaproveita os trechos já renderizados.
- As cenas de cada episódio ainda são código (`cenas.js`); o esquema declarativo fica para a #33.
- O símbolo do peba existe no `site.py` e de novo no motor.
- O JavaScript do motor não tem testes automatizados; a revisão é por quadro.
