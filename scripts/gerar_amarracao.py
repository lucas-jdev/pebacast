"""Gera o cordão de sisal que amarra a etiqueta da saga aos cards do site.

O desenho é o mesmo em todo card, então sai em dois SVGs estáticos: a frente (furos e a perna
que passa por cima) e o verso (a perna que contorna a ponta da etiqueta e some atrás do card).
As sementes são fixas para o resultado não mudar entre execuções.

    python scripts/gerar_amarracao.py
"""

import math
import random
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "site"
LARGURA, ALTURA = 320, 260
ORIGEM_DO_CARD = (90, 130)

BASE = "#c99459"
ESCURO = "#9c6a36"
CLARO = "#e6bd84"
CONTORNO = "#6a4520"
FIAPOS = ("#deb071", "#d2a160", "#efd09c", "#c18d50", "#e6bd80")

ETIQUETA = {"esquerda": 26, "topo": -44, "furo": (18, 21)}
FURO_DO_CARD = (24, 28)


def _cubica(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))


def _amostrar(segmentos, passo=0.8):
    pontos = []
    for indice, (p0, p1, p2, p3) in enumerate(segmentos):
        comprimento = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        n = max(4, int(comprimento / passo))
        ultimo = indice == len(segmentos) - 1
        pontos += [_cubica(p0, p1, p2, p3, i / n) for i in range(n + (1 if ultimo else 0))]
    amostras = []
    for i, ponto in enumerate(pontos):
        antes, depois = pontos[max(0, i - 1)], pontos[min(len(pontos) - 1, i + 1)]
        dx, dy = depois[0] - antes[0], depois[1] - antes[1]
        norma = math.hypot(dx, dy) or 1
        amostras.append((ponto, (dx / norma, dy / norma)))
    return amostras


def _caminho(segmentos):
    x, y = segmentos[0][0]
    partes = [f"M{x:.1f} {y:.1f}"]
    for _, p1, p2, p3 in segmentos:
        partes.append(f"C{p1[0]:.1f} {p1[1]:.1f} {p2[0]:.1f} {p2[1]:.1f} {p3[0]:.1f} {p3[1]:.1f}")
    return " ".join(partes)


def _fiapo(rng, x, y, angulo, comprimento):
    curva = rng.uniform(-0.6, 0.6)
    mx = x + math.cos(angulo + curva) * comprimento * 0.55
    my = y + math.sin(angulo + curva) * comprimento * 0.55
    fx, fy = x + math.cos(angulo) * comprimento, y + math.sin(angulo) * comprimento
    return (f'<path d="M{x:.1f} {y:.1f}Q{mx:.1f} {my:.1f} {fx:.1f} {fy:.1f}" fill="none" stroke="{rng.choice(FIAPOS)}" '
            f'stroke-width="{rng.uniform(0.35, 0.75):.2f}" stroke-linecap="round" opacity="{rng.uniform(0.7, 1):.2f}"/>')


def cordao(segmentos, semente, largura=4.6):
    """Fio de sisal torcido em duas pernas, com fiapos curtos e espetados saindo dos lados."""
    rng = random.Random(semente)
    caminho = _caminho(segmentos)
    amostras = _amostrar(segmentos)
    partes = [
        (f'<path d="{caminho}" fill="none" stroke="#2a1a0b" stroke-opacity="0.32" stroke-width="{largura + 1:.1f}" '
         f'stroke-linecap="round" transform="translate(1.6 2.2)"/>'),
        f'<path d="{caminho}" fill="none" stroke="{CONTORNO}" stroke-width="{largura + 1.5:.1f}" stroke-linecap="round"/>',
        f'<path d="{caminho}" fill="none" stroke="{BASE}" stroke-width="{largura:.1f}" stroke-linecap="round"/>',
    ]

    meia = largura / 2 - 0.25
    percorrido, proxima_torcao = 0.0, 0.0
    for i, ((x, y), (tx, ty)) in enumerate(amostras):
        if i:
            percorrido += math.dist(amostras[i - 1][0], (x, y))
        if percorrido < proxima_torcao:
            continue
        proxima_torcao = percorrido + 3.1
        nx, ny = -ty, tx
        a = (x + nx * meia - tx * 1.5, y + ny * meia - ty * 1.5)
        b = (x - nx * meia + tx * 1.5, y - ny * meia + ty * 1.5)
        controle = (x + tx * 2.2, y + ty * 2.2)
        partes.append(f'<path d="M{a[0]:.1f} {a[1]:.1f}Q{controle[0]:.1f} {controle[1]:.1f} {b[0]:.1f} {b[1]:.1f}" '
                      f'fill="none" stroke="{ESCURO}" stroke-width="1.1" stroke-linecap="round"/>')
        c = (a[0] + tx * 1.15, a[1] + ty * 1.15)
        d = (b[0] + tx * 1.15, b[1] + ty * 1.15)
        brilho = (controle[0] + tx * 1.15, controle[1] + ty * 1.15)
        partes.append(f'<path d="M{c[0]:.1f} {c[1]:.1f}Q{brilho[0]:.1f} {brilho[1]:.1f} {d[0]:.1f} {d[1]:.1f}" '
                      f'fill="none" stroke="{CLARO}" stroke-width="0.8" stroke-linecap="round" opacity="0.85"/>')

    for _ in range(int(percorrido / 1.15)):
        (x, y), (tx, ty) = rng.choice(amostras)
        lado = rng.choice((-1, 1))
        nx, ny = -ty * lado, tx * lado
        tamanho = rng.uniform(1.5, 5) if rng.random() < 0.82 else rng.uniform(6, 11)
        partes.append(_fiapo(rng, x + nx * meia, y + ny * meia, math.atan2(ny, nx) + rng.uniform(-1.15, 1.15), tamanho))
    return "".join(partes)


def furo(x, y, raio=4.6):
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{raio + 1.1:.1f}" fill="#15110c" opacity="0.55"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{raio}" fill="#2a1d10"/>'
            f'<path d="M{x - raio * 0.8:.1f} {y + raio * 0.45:.1f}A{raio} {raio} 0 0 0 {x + raio * 0.8:.1f} {y + raio * 0.45:.1f}" '
            f'fill="none" stroke="#fff6e0" stroke-opacity="0.45" stroke-width="1"/>')


def borda_do_furo(x, y, raio, entrada):
    """Lábio do furo por cima do cordão, deixando aberto só o lado por onde o fio entra."""
    inicio, fim = math.radians(entrada + 40), math.radians(entrada + 320)
    p0 = (x + math.cos(inicio) * raio, y + math.sin(inicio) * raio)
    p1 = (x + math.cos(fim) * raio, y + math.sin(fim) * raio)
    return (f'<path d="M{p0[0]:.1f} {p0[1]:.1f}A{raio} {raio} 0 1 1 {p1[0]:.1f} {p1[1]:.1f}" fill="none" '
            f'stroke="#15110c" stroke-width="1.6" stroke-linecap="round"/>')


def _furo_da_etiqueta():
    """A etiqueta gira em torno do próprio furo (transform-origin no CSS), então o furo não sai do lugar."""
    u, v = ETIQUETA["furo"]
    return ETIQUETA["esquerda"] + u, ETIQUETA["topo"] + v


def _angulo(de, para):
    return math.degrees(math.atan2(para[1] - de[1], para[0] - de[0]))


def _svg(conteudo):
    dx, dy = ORIGEM_DO_CARD
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{ALTURA}" viewBox="0 0 {LARGURA} {ALTURA}">'
            f'<g transform="translate({dx} {dy})">{conteudo}</g></svg>\n')


def gerar():
    furo_tag = _furo_da_etiqueta()
    hx, hy = furo_tag
    cx, cy = FURO_DO_CARD
    canto = (max(cx - 17, -6), 0)
    frente = [(furo_tag, (hx - 6, hy + 14), (cx + 10, cy - 18), FURO_DO_CARD)]
    verso = [(furo_tag, (hx - 22, hy - 12), (canto[0] - 6, hy - 14), canto),
             (canto, (canto[0] + 2, 14), (cx - 8, cy - 2), FURO_DO_CARD)]
    svg_frente = "".join([
        furo(*furo_tag, raio=4.4), furo(*FURO_DO_CARD), cordao(frente, 71),
        borda_do_furo(*furo_tag, raio=4.4, entrada=_angulo(furo_tag, frente[0][1])),
        borda_do_furo(*FURO_DO_CARD, raio=4.6, entrada=_angulo(FURO_DO_CARD, frente[0][2])),
    ])
    (DESTINO / "amarracao-frente.svg").write_text(_svg(svg_frente), encoding="utf-8")
    (DESTINO / "amarracao-verso.svg").write_text(_svg(cordao(verso, 72)), encoding="utf-8")


if __name__ == "__main__":
    gerar()
