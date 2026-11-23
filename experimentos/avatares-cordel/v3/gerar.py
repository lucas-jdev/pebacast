import base64
import io
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TINTA = "#15110c"
PAPEL = "#f3ead6"
FONTES = Path(__file__).resolve().parents[3] / "site" / "fontes"
SAIDA = Path(__file__).parent / "saida"
ESCALA = {"traco": 1.0}

ROSTOS = {
    "oval": "M158 172C156 120 244 120 242 172C242 222 224 260 200 265C176 260 158 222 158 172Z",
    "redondo": "M154 176C152 116 248 116 246 176C246 228 228 258 200 262C172 258 154 228 154 176Z",
    "longo": "M162 168C156 98 244 98 238 168C238 226 222 270 200 274C178 270 162 226 162 168Z",
    "quadrado": "M152 172C150 108 250 108 248 172L246 222C240 252 224 266 200 268C176 266 160 252 154 222Z",
    "coracao": "M156 168C154 114 246 114 244 168C242 212 222 254 200 264C178 254 158 212 156 168Z",
    "largo": "M154 174C150 116 250 116 246 174C246 228 228 262 200 266C172 262 154 228 154 174Z",
}

NARIZES = {
    "reto": "L199 210Q205 217 212 210",
    "cunha": "L197 206L191 212Q201 219 211 212",
    "largo": "L198 202Q186 206 189 213Q200 220 211 213Q214 206 204 202",
    "curvo": "Q207 186 203 208Q207 216 214 209",
}


@dataclass(frozen=True)
class Tom:
    pele: str
    linha: str
    pontilhado: bool


CLARO = Tom(PAPEL, TINTA, False)
MEDIO = Tom(PAPEL, TINTA, True)
ESCURO = Tom(TINTA, PAPEL, False)


@dataclass(frozen=True)
class Persona:
    id: str
    nome: str
    cor: str
    tom: Tom
    figura: Callable[["Persona"], str]
    objeto: Callable[[], str]
    canto: tuple[int, int]


def forma(d, cor=TINTA, contorno=None, largura=3):
    borda = f' stroke="{contorno}" stroke-width="{largura * ESCALA["traco"]:.1f}" stroke-linejoin="round"' if contorno else ""
    return f'<path d="{d}" fill="{cor}"{borda}/>'


def traco(d, largura=3.5, cor=TINTA, escalar=True):
    espessura = largura * ESCALA["traco"] if escalar else largura
    return (f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="{espessura:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def circulo(x, y, r, cor=TINTA, contorno=None, largura=3):
    borda = f' stroke="{contorno}" stroke-width="{largura * ESCALA["traco"]:.1f}"' if contorno else ""
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{cor}"{borda}/>'


def talho(x1, y1, x2, y2, largura=4, cor=PAPEL):
    dx, dy = x2 - x1, y2 - y1
    comprimento = math.hypot(dx, dy) or 1
    meio = largura * ESCALA["traco"] / 2
    nx, ny = -dy / comprimento * meio, dx / comprimento * meio
    return f'<path d="M{x1 + nx:.1f} {y1 + ny:.1f}L{x2:.1f} {y2:.1f}L{x1 - nx:.1f} {y1 - ny:.1f}Z" fill="{cor}"/>'


def talhos(linhas, largura=4, cor=PAPEL):
    return "".join(talho(*linha, largura=largura, cor=cor) for linha in linhas)


def estrela(x, y, r, cor=PAPEL):
    return talhos([(x - r, y, x + r * 0.2, y), (x + r, y, x - r * 0.2, y), (x, y - r, x, y + r * 0.2), (x, y + r, x, y - r * 0.2)], 2.6, cor)


def lua(x, y, r, cor=PAPEL):
    return forma(f"M{x} {y - r}A{r} {r} 0 1 0 {x} {y + r}A{r * 1.25} {r * 1.25} 0 0 1 {x} {y - r}Z", cor)


def busto(roupa="", ombro=1.0):
    def x(v):
        return 200 + (v - 200) * ombro
    d = f"M{x(84)} 440C{x(88)} 346 {x(134)} 304 184 294L216 294C{x(266)} 304 {x(312)} 346 {x(316)} 440"
    return forma(d + "Z") + traco(d, 3.5, PAPEL) + roupa


def dobras(ombro=1.0):
    def x(v):
        return 200 + (v - 200) * ombro
    return talhos([(x(110), 362, x(134), 328), (x(124), 386, x(146), 346), (x(290), 362, x(266), 328), (x(276), 386, x(254), 346)])


def pescoco(tom, largura=16):
    contorno = PAPEL if tom is ESCURO else TINTA
    return (forma(f"M{200 - largura} 248L{200 - largura} 298L{200 + largura} 298L{200 + largura} 248Z", tom.pele, contorno, 3.5)
            + traco(f"M{200 - largura + 2} 270Q200 280 {200 + largura - 2} 270", 3, tom.linha))


def rosto(p, formato="oval"):
    d = ROSTOS[formato]
    tom = p.tom
    contorno = PAPEL if tom is ESCURO else TINTA
    espessura = 6 if tom is ESCURO else 4.5
    orelhas = "".join(f'<ellipse cx="{x}" cy="186" rx="8" ry="14" fill="{tom.pele}" stroke="{contorno}" stroke-width="{3.5 * ESCALA["traco"]:.1f}"/>'
                      for x in (157, 243))
    pele = forma(d, tom.pele, contorno, espessura)
    if not tom.pontilhado:
        return orelhas + pele
    passo = 5 * ESCALA["traco"] ** 0.5
    raio = 1.15 * ESCALA["traco"] ** 0.6
    pontos = (f'<pattern id="pontos-{p.id}" width="{passo:.2f}" height="{passo * 1.732:.2f}" patternUnits="userSpaceOnUse">'
              f'<circle cx="{passo / 4:.2f}" cy="{passo * 0.433:.2f}" r="{raio:.2f}" fill="{TINTA}"/>'
              f'<circle cx="{passo * 0.75:.2f}" cy="{passo * 1.3:.2f}" r="{raio:.2f}" fill="{TINTA}"/></pattern>')
    return orelhas + pele + pontos + forma(d, f"url(#pontos-{p.id})") + traco(d, espessura)


def feicoes(tom, nariz="reto", boca="serena", sobrancelha_dir="M204 166Q220 160 236 168", olhar="aberto", olho_contido=None):
    linha = tom.linha
    reforco = PAPEL if tom.pontilhado else None
    if tom is ESCURO if olho_contido is None else olho_contido:
        olho = "M170 182Q181 176 193 182Q181 186 170 182Z", "M207 182Q219 176 230 182Q219 186 207 182Z"
        pupila_r, pupila_y = 3.2, 181
    else:
        olho = "M168 181Q181 170 195 181Q181 189 168 181Z", "M205 181Q219 170 232 181Q219 189 205 181Z"
        pupila_r, pupila_y = 4.2, 180
    olhos = "".join(forma(d, PAPEL, linha, 2.6) for d in olho) + circulo(182, pupila_y, pupila_r) + circulo(218, pupila_y, pupila_r)
    if olhar == "relaxado":
        olhos += traco("M168 180Q181 173 195 180M205 180Q219 173 232 180", 4, linha)
    caminho_nariz = "M166 168Q180 159 197 166" + NARIZES[nariz]
    bocas = {
        "aberta": forma("M182 230Q200 248 218 230Q200 237 182 230Z", linha) + traco("M182 230Q200 237 218 230", 3, linha),
        "calorosa": traco("M184 232Q200 242 216 232", 4, linha),
        "canto": traco("M186 235Q205 239 218 228", 4, linha),
        "serena": traco("M189 235Q200 238 211 235", 4, linha),
        "seca": traco("M186 236L210 236L217 232", 4, linha),
        "labios": traco("M184 232Q192 228 200 231Q208 228 216 232", 3.2, linha) + traco("M188 237Q200 243 212 237", 3.2, linha),
        "sorriso_contido": traco("M187 232Q200 240 213 232", 4, linha),
        "sorriso_labios": traco("M185 231Q200 240 215 231", 3.6, linha) + traco("M191 240Q200 244 209 240", 2.8, linha),
        "nenhuma": "",
    }
    fundo = (traco(caminho_nariz, 7, reforco) + traco(sobrancelha_dir, 7, reforco)) if reforco else ""
    return fundo + olhos + traco(caminho_nariz, 4, linha) + traco(sobrancelha_dir, 4.5, linha) + bocas[boca]


def nuvem(cor, ondas=True, raio=136, cx=200, cy=200, chave=""):
    bolhas = [(cx, cy, raio)] + [(cx + raio * math.cos(a), cy + raio * 0.92 * math.sin(a), raio * 0.33)
                                 for a in (math.tau * i / 11 + 0.2 for i in range(11))]
    circulos = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>' for x, y, r in bolhas)
    linhas = "".join(
        traco(f"M{cx - raio * 1.5:.0f} {y}" + "".join(f"q12 {(-3 if i % 2 else 3)} 24 0" for i in range(int(raio * 3 / 24) + 2)), 3, PAPEL)
        for y in range(int(cy - raio * 1.4), int(cy + raio * 1.4), 16)
    ) if ondas else ""
    identificador = f"nuvem-{cor[1:]}{chave}"
    return (f'<clipPath id="{identificador}">{circulos}</clipPath>'
            f'<g clip-path="url(#{identificador})"><rect x="-200" y="-200" width="1000" height="1200" fill="{cor}"/>{linhas}</g>')


def ceu(canto):
    pontos = [(52, 54, 7), (110, 36, 5), (300, 40, 6), (352, 70, 8), (40, 150, 5), (366, 160, 6),
              (70, 236, 4), (340, 250, 5), (140, 64, 3), (262, 54, 3), (30, 296, 4), (372, 320, 4)]
    return "".join(estrela(x, y, r) if r > 4 else circulo(x, y, r * 0.55, PAPEL)
                   for x, y, r in pontos if abs(x - canto[0]) > 60 or abs(y - canto[1]) > 60)


def moldura(tamanho=400, quadro=12):
    casas = "".join(f'<rect x="{x}" y="{y}" width="{quadro}" height="{quadro}" fill="{PAPEL}"/>'
                    for i in range(0, tamanho, quadro * 2)
                    for x, y in ((i, 0), (i, tamanho - quadro), (0, i), (tamanho - quadro, i)))
    return (f'<rect width="{tamanho}" height="{tamanho}" fill="none" stroke="{TINTA}" stroke-width="{quadro * 2}"/>{casas}'
            f'<rect x="{quadro + 4}" y="{quadro + 4}" width="{tamanho - 2 * quadro - 8}" height="{tamanho - 2 * quadro - 8}" fill="none" stroke="{PAPEL}" stroke-width="2.5"/>')


def goiva(semente, intensidade=3.2):
    return (f'<filter id="goiva-{semente}" x="-5%" y="-5%" width="110%" height="110%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="{semente}"/>'
            f'<feDisplacementMap in="SourceGraphic" scale="{intensidade}" xChannelSelector="R" yChannelSelector="G"/></filter>')


def davi(p):
    tufos = [(160, 150, 13), (168, 128, 15), (184, 112, 16), (204, 106, 17), (224, 112, 15), (240, 128, 14), (246, 150, 11),
             (196, 124, 13), (214, 126, 12), (178, 134, 11), (230, 140, 10)]
    tampa = forma("M156 176C150 118 184 104 202 104C226 104 254 118 244 176C238 156 228 144 214 140Q206 146 198 140Q186 146 176 142C166 148 160 160 156 176Z")
    cachos = "".join(circulo(x, y, r, TINTA, PAPEL, 2.2) for x, y, r in tufos[:7]) + "".join(circulo(x, y, r) for x, y, r in tufos[7:])
    espirais = "".join(traco(f"M{x - 4} {y}a4 4 0 1 1 4 4", 2, PAPEL) for x, y, _ in tufos[1:6] + tufos[7:9])
    fone = (traco("M150 190C144 92 256 92 250 190", 12, PAPEL) + traco("M150 190C144 92 256 92 250 190", 7)
            + forma("M138 166h22v46h-22z", TINTA, PAPEL, 3) + forma("M240 166h22v46h-22z", TINTA, PAPEL, 3)
            + talhos([(144, 172, 144, 204), (256, 172, 256, 204)], 4))
    camiseta = traco("M182 296Q200 314 218 296", 4, PAPEL) + talhos([(150, 330, 172, 330), (228, 330, 250, 330)], 3)
    return (busto(camiseta + dobras()) + pescoco(p.tom) + rosto(p, "redondo") + tampa + cachos + espirais
            + feicoes(p.tom, "largo", "aberta", "M204 162Q220 152 236 162") + fone)


def davi_objeto():
    microfone = (forma("M52 64a18 24 0 0 1 36 0v22a18 24 0 0 1-36 0z", PAPEL)
                 + talhos([(56, 60, 84, 60), (55, 70, 85, 70), (55, 80, 85, 80), (56, 90, 84, 90)], 3, TINTA)
                 + traco("M44 84q0 30 26 30t26-30M70 114v18M54 134h32", 4.5, PAPEL))
    return microfone + traco("M100 54q10 16 0 32M110 46q16 24 0 48", 3.5, PAPEL)


def helena(p):
    tras = forma("M200 100C150 96 122 128 128 178C120 200 138 214 126 234C118 252 132 266 124 282L172 282"
                 "C158 262 166 240 156 218C150 200 154 186 154 176L246 176C246 186 250 200 244 218C234 240 242 262 228 282L276 282"
                 "C268 266 282 252 274 234C262 214 280 200 272 178C278 128 250 96 200 100Z", TINTA, PAPEL, 3)
    ondas = "".join(traco(d, 2.6, PAPEL) for d in ("M138 198q10 10 2 22", "M134 234q10 10 2 22", "M148 210q8 10 2 20",
                                                   "M262 198q-10 10-2 22", "M266 234q-10 10-2 22", "M252 210q-8 10-2 20"))
    franja = forma("M154 176C150 124 172 104 200 104C236 102 262 124 250 172C244 142 228 128 206 128C196 130 188 136 182 144"
                   "C176 134 172 126 170 120C162 132 156 150 154 176Z", TINTA, PAPEL, 3)
    grisalho = talhos([(192, 110, 248, 146), (200, 118, 244, 154), (196, 114, 236, 126)], 5)
    marcas = traco("M236 186L244 182M236 192L244 193M164 186L156 182", 2.2) + traco("M181 218Q176 224 178 232", 2.2)
    roupa = (forma("M184 296L200 318L216 296Z", PAPEL) + forma("M184 296L170 314L192 310Z", PAPEL, TINTA, 2.5)
             + forma("M216 296L230 314L208 310Z", PAPEL, TINTA, 2.5) + traco("M170 314L190 400M230 314L210 400", 4, PAPEL))
    return (tras + ondas + busto(roupa + dobras(0.94), 0.94) + pescoco(p.tom, 15) + rosto(p, "oval") + franja + grisalho + marcas
            + feicoes(p.tom, "curvo", "canto", "M204 160Q220 148 238 158"))


def helena_objeto():
    poste = traco("M74 132V54M58 134h32", 4.5, PAPEL) + circulo(74, 52, 4, PAPEL)
    travessa = traco("M42 66L106 52", 4, PAPEL)
    prato_e = traco("M42 66L32 92M42 66L52 92", 2, PAPEL) + forma("M28 92h28q-2 10-14 10t-14-10z", PAPEL)
    prato_d = traco("M106 52L96 76M106 52L116 76", 2, PAPEL) + forma("M92 76h28q-2 10-14 10t-14-10z", PAPEL)
    return poste + travessa + prato_e + prato_d


def beatriz(p):
    angulos = [math.pi * 0.78 + i * math.pi * 1.44 / 12 for i in range(13)]
    volume = circulo(200, 160, 82, TINTA, PAPEL, 3) + "".join(circulo(200 + 84 * math.cos(a), 168 + 80 * math.sin(a), 26, TINTA, PAPEL, 3) for a in angulos)
    miolo = circulo(200, 160, 80, TINTA) + "".join(circulo(200 + 84 * math.cos(a), 168 + 80 * math.sin(a), 23.5, TINTA) for a in angulos)
    espirais = "".join(traco(f"M{200 + 84 * math.cos(a) - 7:.1f} {168 + 80 * math.sin(a):.1f}a7 7 0 1 1 7 7", 2.6, PAPEL) for a in angulos)
    franja = "".join(circulo(160 + i * 16, 128 + abs(i - 2.5) * 4, 12, TINTA, PAPEL, 2.5) for i in range(6))
    argolas = traco("M157 204a8 10 0 1 0 0.1 0", 3, PAPEL) + traco("M243 204a8 10 0 1 0 0.1 0", 3, PAPEL)
    roupa = (forma("M182 296L200 324L218 296Z", TINTA, PAPEL, 3) + traco("M178 300Q200 332 222 300", 3, PAPEL)
             + "".join(circulo(178 + i * 7.3, 304 + math.sin(i / 6 * math.pi) * 22, 2.6, PAPEL) for i in range(7)) + dobras())
    return (volume + miolo + espirais + busto(roupa) + pescoco(p.tom) + rosto(p, "oval") + franja + argolas
            + feicoes(p.tom, "reto", "calorosa", olho_contido=False))


def beatriz_objeto():
    torre = forma("M330 34L338 34L342 132L326 132Z", PAPEL)
    cabos = traco("M334 40L268 132M334 52L284 132M334 64L300 132M334 40L392 120M334 52L386 132", 2, PAPEL)
    return torre + cabos + forma("M262 132h136v7h-136z", PAPEL)


def rafael(p):
    cabelo = forma("M152 178C144 118 178 100 204 100C232 100 260 118 248 176C244 158 236 146 224 142Q218 154 204 150Q194 158 182 150Q172 158 160 156C156 162 154 170 152 178Z", TINTA, PAPEL, 3)
    cabelo += talhos([(176, 110, 184, 140), (198, 106, 202, 140), (222, 110, 220, 138)], 4)
    barba = forma("M156 206C160 244 180 266 200 268C220 266 240 244 244 206C236 228 218 242 200 242C182 242 164 228 156 206Z", TINTA)
    barba += "".join(circulo(x, y, 1.6, PAPEL) for x, y in [(168, 234), (178, 246), (190, 254), (210, 254), (222, 246), (232, 234), (186, 240), (214, 240), (200, 250)])
    olheiras = traco("M170 193Q181 199 192 193M208 193Q219 199 230 193", 2.4)
    camisa = (forma("M176 294L188 318L200 302Z", PAPEL, TINTA, 2.5) + forma("M224 294L212 318L200 302Z", PAPEL, TINTA, 2.5)
              + traco("M200 304V420", 3, PAPEL) + "".join(circulo(206, y, 3, PAPEL) for y in (326, 352, 378)))
    return (busto(camisa + dobras()) + pescoco(p.tom) + rosto(p, "quadrado") + barba + cabelo + olheiras
            + feicoes(p.tom, "cunha", "seca", "M204 165L234 166", "relaxado"))


def rafael_objeto():
    def torre(x):
        return traco(f"M{x} 136V64M{x - 10} 136L{x} 104L{x + 10} 136M{x - 6} 84h12", 3.5, PAPEL) + circulo(x, 60, 4, PAPEL)
    sinal = traco("M54 70Q70 58 80 66M96 66Q104 58 118 70", 3, PAPEL) + talhos([(84, 60, 92, 72), (92, 60, 84, 72)], 3)
    return torre(44) + torre(128) + sinal


def camila(p):
    rabo = forma("M232 150C262 168 262 238 250 284C244 252 240 214 226 178Z", TINTA, PAPEL, 3)
    rabo += talhos([(238, 172, 250, 250), (246, 178, 254, 238)], 3.5)
    cabelo = forma("M154 176C148 116 182 100 206 102C238 102 258 124 246 176C238 150 222 134 198 134C176 134 162 150 154 176Z", TINTA, PAPEL, 3)
    cabelo += talhos([(172, 112, 196, 130), (190, 106, 214, 128), (214, 108, 234, 132)], 4)
    elastico = forma("M234 150l10 6-4 8-10-6z", PAPEL)
    oculos = (f'<circle cx="181" cy="181" r="16" fill="none" stroke="{TINTA}" stroke-width="4"/>'
              f'<circle cx="219" cy="181" r="16" fill="none" stroke="{TINTA}" stroke-width="4"/>'
              + traco("M197 179Q200 175 203 179", 3.5, escalar=False))
    cardiga = (forma("M184 296L200 312L216 296Z", PAPEL) + forma("M184 296L174 312L194 308Z", PAPEL, TINTA, 2.4)
               + forma("M216 296L226 312L206 308Z", PAPEL, TINTA, 2.4)
               + traco("M176 300L192 420M224 300L208 420", 4, PAPEL) + "".join(circulo(186, y, 2.8, PAPEL) for y in (340, 364, 388)))
    return (rabo + busto(cardiga + dobras(0.9), 0.9) + pescoco(p.tom, 14) + rosto(p, "oval") + cabelo + elastico
            + feicoes(p.tom, "reto", "aberta") + oculos)


def camila_objeto():
    gaveteiro = forma("M296 44h52v86h-52z", PAPEL) + traco("M296 72h52M296 100h52", 3) + "".join(forma(f"M314 {y}h16v5h-16z", TINTA) for y in (56, 84, 112))
    etiqueta = (traco("M330 60Q344 64 348 78", 2.2, PAPEL) + forma("M344 76l18 6-4 20-18-6z", PAPEL)
                + circulo(352, 86, 3.2, TINTA) + forma("M346 98q6-8 11 2z", TINTA))
    return gaveteiro + etiqueta


def jorge(p):
    laterais = (forma("M150 198C142 172 146 150 158 140C160 158 162 178 164 198Z", TINTA, PAPEL, 2.5)
                + forma("M250 198C258 172 254 150 242 140C240 158 238 178 236 198Z", TINTA, PAPEL, 2.5)
                + talhos([(152, 186, 156, 156), (157, 190, 160, 150), (248, 186, 244, 156), (243, 190, 240, 150)], 3))
    barba = forma("M154 196C158 236 178 262 200 264C222 262 242 236 246 196C238 214 226 222 212 222C206 216 194 216 188 222C174 222 162 214 154 196Z", TINTA, PAPEL, 3)
    barba += talhos([(164, 216, 168, 232), (172, 226, 176, 246), (182, 234, 186, 254), (194, 238, 196, 258), (206, 238, 204, 258),
                     (218, 234, 214, 254), (228, 226, 224, 246), (236, 216, 232, 232), (170, 206, 174, 220), (230, 206, 226, 220)], 3)
    boca = traco("M187 230Q200 235 213 230", 3.5, PAPEL)
    rugas = traco("M176 144Q200 138 224 144M182 153Q200 149 218 153", 2.6, PAPEL) + traco("M176 144Q200 138 224 144M182 153Q200 149 218 153", 2.2)
    cabo = (traco("M330 340C312 302 274 292 250 304C236 312 232 326 234 342", 5, PAPEL)
            + forma("M224 342h20v18h-20z", PAPEL) + talhos([(228, 352, 228, 358), (234, 352, 234, 358), (240, 352, 240, 358)], 2, TINTA))
    gola = traco("M178 296L200 316L222 296", 4.5, PAPEL)
    return (busto(gola + cabo + talhos([(100, 380, 122, 350)]), 1.08) + pescoco(p.tom, 19) + rosto(p, "quadrado")
            + laterais + rugas + feicoes(p.tom, "largo", "nenhuma", "M204 166L236 167") + barba + boca)


def jorge_objeto():
    return lua(326, 86, 40) + circulo(336, 92, 15, TINTA, PAPEL, 3) + traco("M336 92V82M336 92H345", 3, PAPEL)


def yasmin(p):
    cabelo = forma("M156 176C150 118 184 102 208 104C240 106 260 130 252 200C248 180 244 164 236 156"
                   "C216 150 188 148 170 152C164 158 160 166 156 176Z", TINTA, PAPEL, 3)
    franja = forma("M168 152C188 128 238 128 252 200C238 176 214 158 186 158Z", TINTA, PAPEL, 3)
    franja += talhos([(196, 140, 238, 174), (210, 136, 246, 184)], 3.5)
    cabelo += talhos([(176, 116, 192, 132), (196, 110, 210, 128), (218, 112, 230, 130), (236, 122, 246, 140)], 3.5)
    raspado = forma("M155 182C152 168 154 156 162 148L168 156C162 164 160 172 160 184Z", TINTA)
    raspado += "".join(circulo(x, y, 1.2, PAPEL) for x, y in [(157, 172), (160, 164), (158, 178), (163, 158), (162, 170)])
    brincos = circulo(155, 198, 2.6, PAPEL) + circulo(152, 188, 2.2, PAPEL) + circulo(154, 178, 2.2, PAPEL)
    jaqueta = (forma("M178 294L166 318L192 312Z", TINTA, PAPEL, 3) + forma("M222 294L234 318L208 312Z", TINTA, PAPEL, 3)
               + traco("M182 300Q200 316 218 300", 3.5, PAPEL)
               + traco("M168 320L176 420M232 320L224 420", 2.4, PAPEL) + traco("M140 340l4 6M260 340l-4 6", 2.2, PAPEL))
    return (busto(jaqueta + dobras(0.92), 0.92) + pescoco(p.tom, 14) + rosto(p, "coracao") + raspado + cabelo + franja + brincos
            + feicoes(p.tom, "reto", "canto", "M204 160Q220 150 236 158"))


def yasmin_objeto():
    cadeado = (traco("M50 96V80a16 16 0 0 1 32 0", 5, PAPEL) + forma("M40 96h44v38h-44z", PAPEL)
               + circulo(62, 110, 4, TINTA) + forma("M60 112h4v10h-4z", TINTA))
    chave = circulo(104, 70, 9, PAPEL) + circulo(104, 70, 3.4, TINTA) + traco("M110 77L128 96M120 88l6-6M124 92l5-5", 4, PAPEL)
    return cadeado + chave


def otavio(p):
    contorno = ("M152 200C142 178 142 150 150 132Q148 116 164 110Q174 98 192 100Q206 94 220 100Q236 100 242 112Q258 120 254 136"
                "Q262 160 248 200C248 176 244 156 232 142C218 132 182 132 168 142C156 156 152 176 152 200Z")
    fios = "".join(traco(d, 2.3, PAPEL) for d in (
        "M154 190Q150 166 158 146", "M160 182Q156 160 164 144", "M246 190Q250 166 242 146", "M240 182Q244 160 236 144",
        "M158 138Q166 120 184 112", "M168 136Q180 118 200 110", "M182 132Q198 116 218 112", "M198 130Q216 116 236 118",
        "M214 132Q230 122 246 128", "M228 138Q242 134 250 146"))
    cabelo = forma(contorno, TINTA, PAPEL, 3) + fios
    rugas = traco("M180 142Q200 136 220 142M184 151Q200 147 216 151", 2.2, PAPEL)
    oculos = traco("M166 176h28v14h-28zM206 176h28v14h-28zM194 180Q200 177 206 180M166 180L156 176M234 180L244 176", 2, PAPEL, escalar=False)
    sueter = (traco("M174 296L200 340L226 296", 4, PAPEL) + traco("M166 300L200 352L234 300", 2.5, PAPEL)
              + forma("M184 300L200 330L216 300L208 296L200 312L192 296Z", PAPEL)
              + "".join(traco(f"M{x} {y}l4 6", 2, PAPEL) for x, y in [(120, 350), (136, 340), (128, 370), (272, 350), (256, 340), (264, 370)]))
    return (busto(sueter, 1.02) + pescoco(p.tom, 17) + rosto(p, "longo") + cabelo + rugas
            + feicoes(p.tom, "curvo", "sorriso_contido", "M204 168Q220 164 236 170") + oculos)


def otavio_objeto():
    planta = forma("M270 46L356 40L362 124L276 130Z", PAPEL)
    ruas = traco("M284 60L350 56M286 84L352 80M288 108L354 104M300 48L306 126M326 44L332 124", 2.4, TINTA)
    quadras = "".join(forma(f"M{x} {y}h12v10h-12z", TINTA) for x, y in [(288, 64), (312, 88), (336, 62), (290, 112)])
    dobra = traco("M318 42L322 128", 1.6, TINTA)
    return planta + ruas + quadras + dobra


PERSONAS = [
    Persona("davi", "Davi", "#f2c53d", MEDIO, davi, davi_objeto, (76, 90)),
    Persona("helena", "Helena", "#f2a7bf", CLARO, helena, helena_objeto, (72, 90)),
    Persona("beatriz", "Beatriz", "#8ccfc0", ESCURO, beatriz, beatriz_objeto, (310, 86)),
    Persona("rafael", "Rafael", "#a9c8ec", MEDIO, rafael, rafael_objeto, (86, 96)),
    Persona("camila", "Camila", "#c6dc8e", CLARO, camila, camila_objeto, (326, 88)),
    Persona("jorge", "Jorge", "#d8b98a", MEDIO, jorge, jorge_objeto, (326, 86)),
    Persona("yasmin", "Yasmin", "#f2a46b", MEDIO, yasmin, yasmin_objeto, (84, 100)),
    Persona("otavio", "Otávio", "#cdb8ea", ESCURO, otavio, otavio_objeto, (316, 86)),
]

VARIANTES = {
    "completo": dict(caixa="0 0 400 400", moldura=True, objeto=True, ceu=True, ondas=True, traco=1.0, goiva=3.2),
    "cartao": dict(caixa="0 0 400 400", moldura=False, objeto=True, ceu=True, ondas=True, traco=1.0, goiva=3.2),
    "cabeca": dict(caixa="114 94 172 172", moldura=False, objeto=False, ceu=False, ondas=False, traco=1.7, goiva=0),
}


def avatar(p, variante="completo"):
    config = VARIANTES[variante]
    ESCALA["traco"] = config["traco"]
    semente = len(p.id)
    conteudo = ((ceu(p.canto) if config["ceu"] else "") + nuvem(p.cor, config["ondas"])
                + (p.objeto() if config["objeto"] else "") + p.figura(p))
    ESCALA["traco"] = 1.0
    filtro = f' filter="url(#goiva-{semente})"' if config["goiva"] else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{config["caixa"]}" role="img" aria-label="Retrato de {p.nome}">'
            f'<defs>{goiva(semente, config["goiva"])}</defs><rect x="-50" y="-50" width="500" height="500" fill="{TINTA}"/>'
            f'<g{filtro}>{conteudo}</g>{moldura() if config["moldura"] else ""}</svg>')


def fonte_embutida(texto):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    fonte = TTFont(FONTES / "alfa-slab-one-latin-400-normal.woff2")
    recorte = subset.Subsetter()
    recorte.populate(text=texto)
    recorte.subset(fonte)
    fonte.flavor = "woff2"
    buffer = io.BytesIO()
    fonte.save(buffer)
    return f'@font-face{{font-family:"Alfa Slab One";src:url(data:font/woff2;base64,{base64.b64encode(buffer.getvalue()).decode()}) format("woff2")}}'


def coqueiro(x, base, altura, espelho=1):
    tx, ty = x + 18 * espelho, base - altura
    tronco = traco(f"M{x} {base}Q{x + 4 * espelho} {base - altura / 2} {tx} {ty}", 9, PAPEL)
    aneis = talhos([(x + 2 * espelho - 5, base - h, x + 2 * espelho + 5, base - h) for h in range(20, int(altura) - 10, 16)], 2.5, TINTA)
    folhas = ""
    for dx, dy in [(-58, 22), (-44, 46), (58, 22), (44, 46), (-24, -34), (28, -30), (0, 50)]:
        px, py = -dy * 0.18, dx * 0.18
        folhas += forma(f"M{tx} {ty}Q{tx + dx / 2 + px:.1f} {ty + dy / 2 - 16 + py:.1f} {tx + dx} {ty + dy}"
                        f"Q{tx + dx / 2 - px:.1f} {ty + dy / 2 - 16 - py:.1f} {tx} {ty}Z", PAPEL)
        folhas += traco(f"M{tx} {ty}Q{tx + dx / 2:.1f} {ty + dy / 2 - 16:.1f} {tx + dx} {ty + dy}", 1.6)
    return tronco + aneis + folhas


def capa():
    largura, altura = 600, 840
    figura = {p.id: p for p in PERSONAS}
    fileiras = [
        (0.56, [("helena", 96, 318), ("otavio", 232, 290), ("jorge", 368, 290), ("camila", 504, 318)]),
        (0.7, [("beatriz", 122, 450), ("yasmin", 300, 420), ("rafael", 478, 450)]),
        (1.0, [("davi", 300, 600)]),
    ]
    gomos, pessoas = "", ""
    for escala, membros in fileiras:
        for pid, cx, cy in membros:
            p = figura[pid]
            gomos += nuvem(p.cor, True, 112 * escala, cx, cy - 6 * escala, chave=f"-{pid}")
            pessoas += f'<g transform="translate({cx - 200 * escala:.1f} {cy - 190 * escala:.1f}) scale({escala})">{p.figura(p)}</g>'
    estrelas = "".join(estrela(x, y, r) if r > 4 else circulo(x, y, 2.4, PAPEL)
                       for x, y, r in [(60, 150, 8), (130, 120, 4), (200, 150, 6), (420, 130, 4), (540, 200, 8), (80, 240, 4),
                                       (520, 250, 5), (300, 150, 3), (250, 118, 4), (360, 170, 5)])
    ponte = (forma("M486 640L494 640L497 712L483 712Z", PAPEL) + traco("M490 646L436 712M490 660L452 712M490 646L548 712M490 660L532 712", 2, PAPEL)
             + forma("M420 708h150v6h-150z", PAPEL))
    horizonte = forma("M30 712C110 640 180 630 250 712Z", PAPEL) + ponte + coqueiro(54, 800, 150) + coqueiro(552, 800, 140, -1)
    titulo = (f'<rect x="60" y="34" width="480" height="64" fill="{PAPEL}"/>'
              f'<text x="300" y="82" text-anchor="middle" font-family="Alfa Slab One" font-size="44" fill="{TINTA}">PEBACAST</text>'
              + lua(520, 150, 26))
    moldura_capa = "".join(f'<rect x="{x}" y="{y}" width="12" height="12" fill="{PAPEL}"/>'
                           for i in range(0, max(largura, altura), 24)
                           for x, y in ((i, 0), (i, altura - 12), (0, i), (largura - 12, i)) if x < largura and y < altura)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" role="img" aria-label="O elenco do Pebacast">'
            f'<defs><style>{fonte_embutida("PEBACAST")}</style>{goiva(9)}</defs><rect width="{largura}" height="{altura}" fill="{TINTA}"/>'
            f'<g filter="url(#goiva-9)">{estrelas}{horizonte}{gomos}{pessoas}</g>{titulo}'
            f'<rect width="{largura}" height="{altura}" fill="none" stroke="{TINTA}" stroke-width="24"/>{moldura_capa}'
            f'<rect x="16" y="16" width="{largura - 32}" height="{altura - 32}" fill="none" stroke="{PAPEL}" stroke-width="2.5"/></svg>')


def recorte_redondo(svg, destino, tamanho):
    png = destino.with_suffix(".tmp.png")
    subprocess.run(["rsvg-convert", "-w", str(tamanho), str(svg), "-o", str(png)], check=True)
    centro, raio = tamanho // 2, tamanho // 2 - 1
    subprocess.run(["convert", str(png), "(", "+clone", "-alpha", "extract", "-fill", "black", "-colorize", "100",
                    "-fill", "white", "-draw", f"circle {centro},{centro} {centro},{centro - raio}", ")",
                    "-alpha", "off", "-compose", "CopyOpacity", "-composite", str(destino)], check=True)
    png.unlink()


def main():
    for variante in VARIANTES:
        (SAIDA / variante).mkdir(parents=True, exist_ok=True)
    pngs, redondos = [], []
    for p in PERSONAS:
        for variante in VARIANTES:
            (SAIDA / variante / f"{p.id}.svg").write_text(avatar(p, variante), encoding="utf-8")
        png = SAIDA / f"{p.id}.png"
        subprocess.run(["rsvg-convert", "-w", "600", str(SAIDA / "completo" / f"{p.id}.svg"), "-o", str(png)], check=True)
        pngs.append(str(png))
        redondo = SAIDA / "cabeca" / f"{p.id}.png"
        recorte_redondo(SAIDA / "cabeca" / f"{p.id}.svg", redondo, 240)
        redondos.append(str(redondo))
    subprocess.run(["montage", *pngs, "-tile", "4x2", "-geometry", "+16+16", "-background", PAPEL, str(SAIDA / "galeria.png")], check=True)
    subprocess.run(["montage", *redondos, "-tile", "8x1", "-geometry", "64x64+6+6", "-background", PAPEL, "/tmp/r64.png"], check=True)
    subprocess.run(["montage", *redondos, "-tile", "8x1", "-geometry", "34x34+4+4", "-background", PAPEL, "/tmp/r34.png"], check=True)
    subprocess.run(["convert", "/tmp/r64.png", "(", "/tmp/r34.png", "-gravity", "west", "-background", PAPEL, "-extent", "608x46", ")",
                    "-append", str(SAIDA / "redondos-64-34.png")], check=True)
    (SAIDA / "capa-elenco.svg").write_text(capa(), encoding="utf-8")
    subprocess.run(["rsvg-convert", "-w", "900", str(SAIDA / "capa-elenco.svg"), "-o", str(SAIDA / "capa-elenco.png")], check=True)


if __name__ == "__main__":
    main()
