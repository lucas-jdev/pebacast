"""Gera as imagens da conferência à mão: 6 s em volta de cada fronteira prevista entre personas.

Cada painel tem o espectrograma (0 a 4 kHz), o F0 (pontos amarelos, 60 a 400 Hz, escala à direita),
a fronteira prevista (linha vermelha), as palavras que o Vosk ouviu com o tempo delas e, no título,
o fim do turno anterior e o começo do seguinte segundo o roteiro. A fronteira está certa quando a
linha cai na pausa entre o fim do turno anterior e o começo do seguinte.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from medir import f0_yin  # noqa: E402
from segmentacao import TAXA, decodificar  # noqa: E402

LARGURA, ALTURA, JANELA_S = 900, 230, 6.0


def espectrograma(x: np.ndarray) -> np.ndarray:
    n, passo = 512, 80
    quadros = np.lib.stride_tricks.sliding_window_view(x, n)[::passo] * np.hanning(n)
    s = np.abs(np.fft.rfft(quadros, axis=1))[:, : n * 4000 // TAXA]
    db = 20 * np.log10(s + 1e-6)
    db = np.clip((db - db.max() + 70) / 70, 0, 1)
    return (db.T[::-1] * 255).astype(np.uint8)


def painel(x, centro, palavras, titulo):
    a = max(0.0, centro - JANELA_S / 2)
    trecho = x[int(a * TAXA):int((a + JANELA_S) * TAXA)]
    img = Image.fromarray(espectrograma(trecho)).resize((LARGURA, ALTURA - 60)).convert("RGB")
    tela = Image.new("RGB", (LARGURA, ALTURA), "white")
    tela.paste(img, (0, 40))
    d = ImageDraw.Draw(tela)
    d.text((4, 2), titulo[:150], fill="black")
    d.text((4, 16), titulo[150:300], fill="black")
    f0 = f0_yin(trecho)
    for i, f in enumerate(f0):
        if f > 0:
            px = int((i * 0.01 + 0.016) / JANELA_S * LARGURA)
            py = 40 + int((1 - (f - 60) / 340) * (ALTURA - 60))
            d.ellipse((px - 1, py - 1, px + 1, py + 1), fill="yellow")
    xc = int((centro - a) / JANELA_S * LARGURA)
    d.line((xc, 40, xc, ALTURA - 20), fill="red", width=2)
    for p in palavras:
        if a <= p["start"] < a + JANELA_S:
            px = int((p["start"] - a) / JANELA_S * LARGURA)
            d.text((px, ALTURA - 18), p["word"], fill="blue")
    return tela


def ultimas(texto, n=6):
    return " ".join(texto.split()[-n:])


def primeiras(texto, n=6):
    return " ".join(texto.split()[:n])


if __name__ == "__main__":
    raiz, audio, saida, ep, quantas = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5])
    sys.path.insert(0, str(raiz / "src"))
    from podcast.personas import carregar_personas
    from podcast.publicacao import falas_do_episodio
    from podcast.roteiro import Projeto

    projeto = Projeto(raiz)
    falas = falas_do_episodio(projeto.episodios / ep, carregar_personas(raiz / "curriculum" / "personas"),
                              projeto.config()["tts"])
    seg = json.loads((saida / f"{ep}.segmentos.json").read_text(encoding="utf-8"))["turnos"]
    palavras = json.loads((saida / f"{ep}.palavras.json").read_text(encoding="utf-8"))
    x = decodificar(audio / f"pebacast-{ep}.mp3")
    trocas = [t for t in seg[1:] if t["persona"] != seg[t["indice"] - 1]["persona"]]
    escolhidas = [trocas[i] for i in np.linspace(0, len(trocas) - 1, quantas).round().astype(int)]
    paineis = []
    for n, t in enumerate(escolhidas, start=1):
        antes, depois = falas[t["indice"] - 1], falas[t["indice"]]
        titulo = (f"#{n} turno {t['indice']} ({antes.persona.id}->{depois.persona.id}) em {t['inicio']:.1f}s | "
                  f"FIM: ...{ultimas(antes.texto)} | COMECO: {primeiras(depois.texto)}...")
        paineis.append(painel(x, t["inicio"], palavras, titulo))
    for g in range(0, len(paineis), 5):
        grupo = paineis[g:g + 5]
        folha = Image.new("RGB", (LARGURA, ALTURA * len(grupo)), "white")
        for i, p in enumerate(grupo):
            folha.paste(p, (0, i * ALTURA))
        folha.save(saida / f"{ep}.fronteiras-{g // 5 + 1}.png")
    print(ep, len(trocas), "trocas de persona;", len(escolhidas), "conferidas")
