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

ROSTO = "M158 172C156 120 244 120 242 172C242 222 224 260 200 265C176 260 158 222 158 172Z"


@dataclass(frozen=True)
class Tom:
    pele: str
    linha: str
    hachura: bool


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


def forma(d, cor=TINTA, contorno=None, largura=3):
    borda = f' stroke="{contorno}" stroke-width="{largura}" stroke-linejoin="round"' if contorno else ""
    return f'<path d="{d}" fill="{cor}"{borda}/>'


def traco(d, largura=3.5, cor=TINTA):
    return f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="{largura}" stroke-linecap="round" stroke-linejoin="round"/>'


def circulo(x, y, r, cor=TINTA, contorno=None, largura=3):
    borda = f' stroke="{contorno}" stroke-width="{largura}"' if contorno else ""
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{cor}"{borda}/>'


def talho(x1, y1, x2, y2, largura=4, cor=PAPEL):
    dx, dy = x2 - x1, y2 - y1
    comprimento = math.hypot(dx, dy) or 1
    nx, ny = -dy / comprimento * largura / 2, dx / comprimento * largura / 2
    return f'<path d="M{x1 + nx:.1f} {y1 + ny:.1f}L{x2:.1f} {y2:.1f}L{x1 - nx:.1f} {y1 - ny:.1f}Z" fill="{cor}"/>'


def talhos(linhas, largura=4, cor=PAPEL):
    return "".join(talho(*linha, largura=largura, cor=cor) for linha in linhas)


def estrela(x, y, r, cor=PAPEL):
    m = r * 0.28
    return forma(f"M{x} {y - r}L{x + m} {y - m}L{x + r} {y}L{x + m} {y + m}L{x} {y + r}L{x - m} {y + m}L{x - r} {y}L{x - m} {y - m}Z", cor)


def lua(x, y, r, cor=PAPEL):
    return forma(f"M{x} {y - r}A{r} {r} 0 1 0 {x} {y + r}A{r * 1.25} {r * 1.25} 0 0 1 {x} {y - r}Z", cor)


def busto(roupa=""):
    return forma("M84 440C88 346 134 304 184 294L216 294C266 304 312 346 316 440Z") + traco("M84 440C88 346 134 304 184 294L216 294C266 304 312 346 316 440", 3.5, PAPEL) + roupa


def pescoco(tom):
    sombra = traco("M186 270Q200 280 214 270", 3, tom.linha)
    return forma("M184 248L184 298L216 298L216 248Z", tom.pele, PAPEL if tom is ESCURO else TINTA, 3.5) + sombra


def rosto(p, d=ROSTO):
    tom = p.tom
    contorno = PAPEL if tom is ESCURO else TINTA
    orelhas = (f'<ellipse cx="157" cy="186" rx="8" ry="14" fill="{tom.pele}" stroke="{contorno}" stroke-width="3.5"/>'
               f'<ellipse cx="243" cy="186" rx="8" ry="14" fill="{tom.pele}" stroke="{contorno}" stroke-width="3.5"/>')
    pele = forma(d, tom.pele, contorno, 4.5)
    if not tom.hachura:
        return orelhas + pele
    pontos = (f'<pattern id="pontos-{p.id}" width="5" height="8.66" patternUnits="userSpaceOnUse">'
              f'<circle cx="1.25" cy="2.16" r="1.25" fill="{TINTA}"/><circle cx="3.75" cy="6.5" r="1.25" fill="{TINTA}"/></pattern>')
    return orelhas + pele + pontos + forma(d, f"url(#pontos-{p.id})") + traco(d, 4.5)


def feicoes(tom, boca="serena", sobrancelha_dir="M204 166Q220 160 236 168", olho_dir=None):
    linha, fundo = tom.linha, tom.pele
    reforco = PAPEL if tom.hachura else None
    olho_e = forma("M168 181Q181 170 195 181Q181 189 168 181Z", PAPEL, linha, 3)
    olho_d = olho_dir if olho_dir is not None else forma("M205 181Q219 170 232 181Q219 189 205 181Z", PAPEL, linha, 3)
    pupilas = circulo(182, 180, 4.2, TINTA) + ("" if olho_dir is not None else circulo(218, 180, 4.2, TINTA))
    nariz = "M166 168Q180 159 197 166L199 210Q205 217 212 210"
    bocas = {
        "aberta": forma("M182 230Q200 248 218 230Q200 237 182 230Z", linha) + traco("M182 230Q200 237 218 230", 3, linha),
        "calorosa": traco("M183 231Q200 243 217 231", 4, linha),
        "canto": traco("M186 235Q205 239 218 228", 4, linha),
        "serena": traco("M188 235Q200 238 212 235", 4, linha),
        "seca": traco("M186 236L210 236L217 232", 4, linha),
        "nenhuma": "",
    }
    fundo_traco = (traco(nariz, 7, reforco) + traco(sobrancelha_dir, 7, reforco)) if reforco else ""
    return (fundo_traco + olho_e + olho_d + pupilas + traco(nariz, 4, linha) + traco(sobrancelha_dir, 4.5, linha) + bocas[boca])


def nuvem(cor, cx=200, cy=196, raio=118):
    bolhas = [(cx, cy, raio)] + [(cx + raio * math.cos(a), cy + raio * 0.92 * math.sin(a), 42)
                                 for a in (math.tau * i / 11 + 0.2 for i in range(11))]
    circulos = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>' for x, y, r in bolhas)
    ondas = "".join(
        traco("M40 {y}".format(y=y) + "".join(f"q10 {(-3 if i % 2 else 3)} 20 0" for i in range(17)), 2.2, PAPEL)
        for y in range(40, 360, 11)
    )
    return (f'<clipPath id="nuvem-{cor[1:]}">{circulos}</clipPath>'
            f'<g clip-path="url(#nuvem-{cor[1:]})"><rect width="400" height="400" fill="{cor}"/>{ondas}</g>')


def ceu(evitar=()):
    pontos = [(52, 54, 7), (110, 36, 5), (300, 40, 6), (352, 70, 8), (40, 150, 5), (366, 160, 6),
              (70, 230, 4), (340, 250, 5), (140, 70, 3), (262, 58, 3), (30, 290, 4), (372, 316, 4)]
    return "".join(estrela(x, y, r) if r > 4 else circulo(x, y, r * 0.6, PAPEL)
                   for x, y, r in pontos if not any(abs(x - ex) < 50 and abs(y - ey) < 50 for ex, ey in evitar))


def moldura(tamanho=400, quadro=12):
    casas = []
    for i in range(0, tamanho, quadro):
        if (i // quadro) % 2 == 0:
            for x, y in ((i, 0), (i, tamanho - quadro), (0, i), (tamanho - quadro, i)):
                casas.append(f'<rect x="{x}" y="{y}" width="{quadro}" height="{quadro}" fill="{PAPEL}"/>')
    return (f'<rect width="{tamanho}" height="{tamanho}" fill="none" stroke="{TINTA}" stroke-width="{quadro * 2}"/>'
            + "".join(casas) + f'<rect x="{quadro + 4}" y="{quadro + 4}" width="{tamanho - 2 * quadro - 8}" height="{tamanho - 2 * quadro - 8}" fill="none" stroke="{PAPEL}" stroke-width="2.5"/>')


def goiva(semente):
    return (f'<filter id="goiva-{semente}" x="-5%" y="-5%" width="110%" height="110%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="{semente}"/>'
            f'<feDisplacementMap in="SourceGraphic" scale="3.2" xChannelSelector="R" yChannelSelector="G"/></filter>')


def davi(p):
    tampa = forma("M154 178C148 112 184 96 200 98C228 96 256 112 246 178C238 148 224 136 200 136C176 136 162 148 154 178Z")
    centros = [(x, y) for y in (108, 124, 142) for x in range(158, 246, 16)
               if ((x - 200) / 50) ** 2 + ((y - 150) / 52) ** 2 < 1.05]
    cachos = "".join(circulo(x + (y % 3) * 2, y, 13, TINTA, PAPEL, 2.5) for x, y in centros)
    espirais = "".join(traco(f"M{x + (y % 3) * 2 - 4} {y}a4 4 0 1 1 4 4", 2, PAPEL) for x, y in centros)
    fone = (traco("M150 190C144 92 256 92 250 190", 12, PAPEL) + traco("M150 190C144 92 256 92 250 190", 7)
            + forma("M138 166h22v46h-22z", TINTA, PAPEL, 3) + forma("M240 166h22v46h-22z", TINTA, PAPEL, 3)
            + talhos([(144, 172, 144, 204), (256, 172, 256, 204)], 4))
    chaves = (traco("M186 326q-9 0-9 9v7q0 7-7 7q7 0 7 7v7q0 9 9 9", 4, PAPEL)
              + traco("M214 326q9 0 9 9v7q0 7 7 7q-7 0-7 7v7q0 9-9 9", 4, PAPEL))
    gola = traco("M182 296Q200 314 218 296", 4, PAPEL)
    return (busto(gola + chaves + talhos([(110, 360, 130, 330), (120, 380, 140, 344), (290, 360, 270, 330), (280, 380, 260, 344)]))
            + pescoco(p.tom) + rosto(p) + tampa + cachos + espirais
            + feicoes(p.tom, "aberta", "M204 164Q220 154 236 164") + fone)


def davi_objeto():
    microfone = (forma("M52 64a18 24 0 0 1 36 0v22a18 24 0 0 1-36 0z", PAPEL)
                 + talhos([(56, 60, 84, 60), (55, 70, 85, 70), (55, 80, 85, 80), (56, 90, 84, 90)], 3, TINTA)
                 + traco("M44 84q0 30 26 30t26-30M70 114v18M54 134h32", 4.5, PAPEL))
    ondas = traco("M100 54q10 16 0 32M110 46q16 24 0 48", 3.5, PAPEL)
    return microfone + ondas


def helena(p):
    tras = forma("M200 100C150 96 122 128 128 178C120 200 138 214 126 234C116 252 134 264 122 282L174 282"
                 "C158 262 166 240 156 218C150 200 154 186 154 176Z", TINTA, PAPEL, 3)
    tras += forma("M200 100C246 96 272 126 262 174L250 172Z", TINTA, PAPEL, 3)
    ondas = "".join(traco(d, 2.6, PAPEL) for d in ("M138 198q10 10 2 22", "M134 234q10 10 2 22", "M148 210q8 10 2 20", "M146 248q8 8 4 20"))
    franja = forma("M154 176C150 124 172 104 200 104C236 102 262 124 254 170C246 142 228 128 206 128C196 130 188 136 182 144"
                   "C176 134 172 126 170 120C162 132 156 150 154 176Z", TINTA, PAPEL, 3)
    grisalho = talhos([(192, 110, 252, 150), (200, 118, 246, 156), (196, 114, 238, 128)], 5)
    lapis = (f'<g transform="rotate(-34 258 160)"><rect x="258" y="155" width="46" height="9" fill="{PAPEL}" stroke="{TINTA}" stroke-width="3"/>'
             f'<path d="M304 155l11 4.5-11 4.5z" fill="{PAPEL}" stroke="{TINTA}" stroke-width="2"/></g>')
    marcas = traco("M236 186L244 182M236 192L244 193M164 186L156 182", 2.2) + traco("M181 218Q176 224 178 232", 2.2)
    roupa = (forma("M184 296L200 318L216 296Z", PAPEL) + forma("M184 296L170 314L192 310Z", PAPEL, TINTA, 2.5)
             + forma("M216 296L230 314L208 310Z", PAPEL, TINTA, 2.5)
             + traco("M170 314L190 400M230 314L210 400", 4, PAPEL)
             + talhos([(110, 360, 134, 326), (124, 384, 146, 344), (290, 360, 266, 326), (276, 384, 254, 344)]))
    return (tras + ondas + busto(roupa) + pescoco(p.tom) + rosto(p) + franja + grisalho + lapis + marcas
            + feicoes(p.tom, "canto", "M204 160Q220 148 238 158"))


def helena_objeto():
    tijolos = "".join(forma(f"M{x} {y}h24v14h-24z", PAPEL) for x, y in
                      [(36, 108), (62, 108), (88, 108), (48, 92), (74, 92), (62, 76)])
    return tijolos + talhos([(40, 115, 56, 115), (66, 99, 80, 99)], 2.5, TINTA)


def beatriz(p):
    angulos = [math.pi * 0.78 + i * math.pi * 1.44 / 12 for i in range(13)]
    volume = circulo(200, 160, 82, TINTA, PAPEL, 3) + "".join(circulo(200 + 84 * math.cos(a), 168 + 80 * math.sin(a), 26, TINTA, PAPEL, 3) for a in angulos)
    miolo = circulo(200, 160, 80, TINTA) + "".join(circulo(200 + 84 * math.cos(a), 168 + 80 * math.sin(a), 23.5, TINTA) for a in angulos)
    espirais = "".join(traco(f"M{200 + 84 * math.cos(a) - 7:.1f} {168 + 80 * math.sin(a):.1f}a7 7 0 1 1 7 7", 2.6, PAPEL) for a in angulos[::1])
    franja = "".join(circulo(160 + i * 16, 128 + abs(i - 2.5) * 4, 12, TINTA, PAPEL, 2.5) for i in range(6))
    argolas = traco("M157 204a8 10 0 1 0 0.1 0", 3, PAPEL) + traco("M243 204a8 10 0 1 0 0.1 0", 3, PAPEL)
    roupa = (forma("M182 296L200 324L218 296Z", TINTA, PAPEL, 3) + traco("M178 300Q200 332 222 300", 3, PAPEL)
             + "".join(circulo(178 + i * 7.3, 304 + math.sin(i / 6 * math.pi) * 22, 2.6, PAPEL) for i in range(7))
             + talhos([(110, 360, 134, 326), (124, 384, 146, 344), (290, 360, 266, 326), (276, 384, 254, 344)]))
    return (volume + miolo + espirais + busto(roupa) + pescoco(p.tom) + rosto(p) + franja + argolas
            + feicoes(p.tom, "calorosa"))


def beatriz_objeto():
    torre = forma("M330 34L338 34L342 132L326 132Z", PAPEL)
    cabos = traco("M334 40L268 132M334 52L284 132M334 64L300 132M334 40L392 120M334 52L386 132", 2, PAPEL)
    return torre + cabos + forma("M262 132h136v7h-136z", PAPEL)


def rafael(p):
    cabelo = forma("M154 178C146 118 178 98 204 100C232 100 258 120 246 176C244 156 236 144 228 140"
                   "C226 150 218 156 210 150C206 160 196 160 190 150C182 158 172 156 168 146C162 156 158 166 154 178Z", TINTA, PAPEL, 3)
    cabelo += talhos([(176, 108, 190, 136), (198, 104, 206, 132), (222, 108, 226, 134)], 4)
    barba = forma("M162 210C166 244 182 262 200 266C218 262 234 244 238 210C230 230 216 244 200 244C184 244 170 230 162 210Z", TINTA)
    barba += "".join(circulo(x, y, 1.6, PAPEL) for x, y in [(172, 234), (182, 246), (194, 254), (206, 254), (218, 246), (228, 234), (188, 238), (212, 238), (200, 248)])
    olheiras = traco("M170 192Q181 198 192 192M208 192Q219 198 230 192", 2.4)
    roupa = (forma("M172 294L188 318L200 302L212 318L228 294Z", TINTA, PAPEL, 3)
             + traco("M200 314V420", 3.5, PAPEL) + "".join(traco(f"M195 {y}h10", 2.2, PAPEL) for y in range(322, 400, 9))
             + talhos([(110, 360, 134, 326), (124, 384, 146, 344), (290, 360, 266, 326), (276, 384, 254, 344)]))
    return (busto(roupa) + pescoco(p.tom) + rosto(p) + barba + cabelo + olheiras
            + feicoes(p.tom, "seca", "M204 165L234 166"))


def rafael_objeto():
    torre = traco("M50 138L66 64L82 138M56 112H76M60 92H72", 4.5, PAPEL) + circulo(66, 60, 5, PAPEL)
    raio = forma("M100 40L88 70L98 70L86 100L112 62L100 62L110 40Z", PAPEL)
    return torre + raio


def camila(p):
    rabo = forma("M232 110C298 92 324 150 304 222C300 186 284 154 252 142Z", TINTA, PAPEL, 3)
    rabo += talhos([(262, 118, 298, 176), (272, 114, 306, 196), (254, 124, 284, 166)], 4)
    elastico = circulo(240, 110, 8, PAPEL) + circulo(240, 110, 3, TINTA)
    cabelo = forma("M154 176C148 116 182 100 206 102C238 102 258 124 246 176C238 150 222 134 198 134C176 134 162 150 154 176Z", TINTA, PAPEL, 3)
    cabelo += talhos([(172, 112, 196, 130), (190, 106, 214, 128), (214, 108, 234, 132)], 4)
    oculos = (f'<circle cx="181" cy="181" r="16" fill="none" stroke="{TINTA}" stroke-width="4"/>'
              f'<circle cx="219" cy="181" r="16" fill="none" stroke="{TINTA}" stroke-width="4"/>' + traco("M197 179Q200 175 203 179", 3.5))
    gola = forma("M176 290Q200 308 224 290L224 312Q200 330 176 312Z", TINTA, PAPEL, 3)
    gola += "".join(traco(f"M{x} {300 + abs(x - 200) * -0.15 + 6}v14", 2.4, PAPEL) for x in range(182, 222, 8))
    return (rabo + elastico + busto(gola + talhos([(110, 360, 134, 326), (124, 384, 146, 344), (290, 360, 266, 326), (276, 384, 254, 344)]))
            + pescoco(p.tom) + rosto(p) + cabelo + feicoes(p.tom, "aberta") + oculos)


def camila_objeto():
    banco = (forma("M310 62a26 9 0 0 1 52 0v44a26 9 0 0 1-52 0z", PAPEL)
             + traco("M310 62a26 9 0 0 0 52 0M310 78a26 9 0 0 0 52 0M310 94a26 9 0 0 0 52 0", 2.5))
    cadeado = (traco("M326 108v-8a10 10 0 0 1 20 0v8", 4, PAPEL) + forma("M318 108h36v28h-36z", PAPEL)
               + circulo(336, 119, 3.5, TINTA) + forma("M334 120h4v8h-4z", TINTA))
    return banco + cadeado


def jorge(p):
    rosto_largo = "M152 176C146 98 254 98 248 176C248 224 228 262 200 266C172 262 152 224 152 176Z"
    laterais = (forma("M150 198C142 172 146 150 158 140C160 158 162 178 164 198Z", TINTA, PAPEL, 2.5)
                + forma("M250 198C258 172 254 150 242 140C240 158 238 178 236 198Z", TINTA, PAPEL, 2.5)
                + talhos([(152, 186, 156, 156), (157, 190, 160, 150), (248, 186, 244, 156), (243, 190, 240, 150)], 3))
    brilho = talhos([(172, 134, 190, 124), (176, 142, 186, 138)], 5)
    cabelo = laterais + brilho
    barba = forma("M156 190C160 244 178 276 200 278C222 276 240 244 244 190C236 210 224 220 212 220C206 214 194 214 188 220C176 220 164 210 156 190Z", TINTA, PAPEL, 3)
    barba += talhos([(172, 230, 178, 258), (186, 240, 190, 268), (200, 246, 200, 272), (214, 240, 210, 268), (228, 230, 222, 258)], 4)
    boca = traco("M186 230Q200 236 214 230", 3.5, PAPEL)
    rugas = traco("M176 144Q200 138 224 144M182 153Q200 149 218 153", 2.6, PAPEL) + traco("M176 144Q200 138 224 144M182 153Q200 149 218 153", 2.2)
    cabo = (traco("M118 330C146 352 170 318 200 346S256 320 286 344", 5, PAPEL)
            + forma("M282 336h16v12h-16z", PAPEL) + talhos([(286, 340, 286, 346), (292, 340, 292, 346)], 2, TINTA))
    gola = traco("M178 296L200 316L222 296", 4.5, PAPEL)
    return (busto(gola + cabo + talhos([(110, 380, 132, 350), (290, 380, 268, 350)])) + pescoco(p.tom) + rosto(p, rosto_largo)
            + cabelo + rugas + feicoes(p.tom, "nenhuma", "M204 166L236 167") + barba + boca)


def jorge_objeto():
    relogio = circulo(336, 92, 15, TINTA, PAPEL, 3) + traco("M336 92V82M336 92H345", 3, PAPEL)
    return lua(326, 86, 40) + relogio


def yasmin(p):
    capuz = forma("M200 92C140 92 120 140 128 200C132 240 140 270 152 296L248 296C260 270 268 240 272 200C280 140 260 92 200 92Z", TINTA, PAPEL, 3.5)
    capuz += talhos([(142, 150, 136, 230), (258, 150, 264, 230), (176, 104, 160, 128), (224, 104, 240, 128)], 4.5)
    franja = forma("M158 178C154 132 176 118 204 118C232 118 248 136 244 170C232 150 214 142 196 146C184 156 170 166 158 178Z", TINTA, PAPEL, 3)
    franja += talhos([(204, 124, 236, 152), (190, 128, 220, 146)], 3.5)
    brinco = circulo(243, 204, 3, PAPEL) + circulo(246, 194, 2.4, PAPEL)
    cordoes = traco("M180 300L176 346M220 300L224 346", 3, PAPEL) + circulo(176, 350, 4, PAPEL) + circulo(224, 350, 4, PAPEL)
    chave = circulo(200, 334, 8, PAPEL) + circulo(200, 334, 3, TINTA) + traco("M200 342V366M200 356h7M200 362h5", 3.5, PAPEL)
    return (capuz + busto(cordoes + chave + talhos([(110, 370, 134, 336), (290, 370, 266, 336)])) + pescoco(p.tom)
            + rosto(p) + franja + brinco + feicoes(p.tom, "canto", "M204 162Q220 154 236 160"))


def yasmin_objeto():
    return forma("M62 44L104 58L62 74Z", PAPEL) + traco("M62 40V140", 5, PAPEL) + talhos([(68, 52, 92, 58)], 3, TINTA)


def otavio(p):
    rosto_longo = "M160 168C154 98 246 98 240 168C240 224 224 266 200 270C176 266 160 224 160 168Z"
    contorno = ("M150 200C140 178 140 150 148 132Q146 116 162 110Q172 98 190 100Q204 94 218 100Q234 100 240 112Q256 120 252 136"
                "Q260 160 250 200C250 176 246 156 234 142C220 132 182 132 166 142C154 156 150 176 150 200Z")
    fios = "".join(traco(d, 2.3, PAPEL) for d in (
        "M152 190Q148 166 156 146", "M158 182Q154 160 162 144", "M248 190Q252 166 244 146", "M242 182Q246 160 238 144",
        "M156 138Q164 120 182 112", "M166 136Q178 118 198 110", "M180 132Q196 116 216 112", "M196 130Q214 116 234 118",
        "M212 132Q228 122 244 128", "M226 138Q240 134 248 146", "M164 128Q170 114 186 106", "M204 104Q220 102 232 110"))
    cabelo = forma(contorno, TINTA, PAPEL, 3) + fios
    rugas = traco("M180 142Q200 136 220 142M184 151Q200 147 216 151", 2.4, PAPEL)
    sobrancelhas = forma("M164 170Q180 160 196 168Q180 166 164 174Z", PAPEL) + forma("M204 168Q220 160 236 170Q220 166 204 172Z", PAPEL)
    oculos = (f'<circle cx="181" cy="183" r="14" fill="none" stroke="{PAPEL}" stroke-width="4.5"/>'
              f'<circle cx="219" cy="183" r="14" fill="none" stroke="{PAPEL}" stroke-width="4.5"/>' + traco("M195 181Q200 177 205 181", 3.5, PAPEL))
    marcas = traco("M160 190L152 186M160 196L152 198M240 190L248 186M240 196L248 198", 2.4, PAPEL) + traco("M180 214Q174 226 180 236M220 214Q226 226 220 236", 2.4, PAPEL)
    sueter = (traco("M174 296L200 340L226 296", 4, PAPEL) + traco("M166 300L200 352L234 300", 2.5, PAPEL)
              + forma("M184 300L200 330L216 300L208 296L200 312L192 296Z", PAPEL)
              + talhos([(190, 304, 194, 312), (206, 304, 210, 312)], 2.5, TINTA)
              + "".join(traco(f"M{x} {y}l4 6", 2, PAPEL) for x, y in [(120, 350), (136, 340), (128, 370), (272, 350), (256, 340), (264, 370), (144, 390), (248, 390)]))
    return (busto(sueter) + pescoco(p.tom) + rosto(p, rosto_longo) + cabelo + rugas + marcas
            + feicoes(p.tom, "calorosa", "M204 166Q220 160 236 168") + sobrancelhas + oculos)


def otavio_objeto():
    duna = forma("M262 136C290 70 330 58 398 126V136Z", PAPEL)
    predios = "".join(forma(f"M{x} 136V{y}h{w}V136Z", PAPEL) for x, y, w in [(268, 104, 12), (284, 92, 10), (298, 110, 12)])
    janelas = talhos([(272, 112, 272, 120), (288, 100, 288, 108), (302, 118, 302, 126)], 3, TINTA)
    return duna + talhos([(320, 84, 350, 104), (340, 80, 372, 108)], 3, TINTA) + predios + janelas


PERSONAS = [
    Persona("davi", "Davi", "#f2c53d", MEDIO, davi, davi_objeto),
    Persona("helena", "Helena", "#f2a7bf", CLARO, helena, helena_objeto),
    Persona("beatriz", "Beatriz", "#8ccfc0", ESCURO, beatriz, beatriz_objeto),
    Persona("rafael", "Rafael", "#a9c8ec", MEDIO, rafael, rafael_objeto),
    Persona("camila", "Camila", "#c6dc8e", CLARO, camila, camila_objeto),
    Persona("jorge", "Jorge", "#d8b98a", MEDIO, jorge, jorge_objeto),
    Persona("yasmin", "Yasmin", "#f2a46b", MEDIO, yasmin, yasmin_objeto),
    Persona("otavio", "Otávio", "#cdb8ea", ESCURO, otavio, otavio_objeto),
]

EVITAR = {"davi": [(70, 90)], "helena": [(60, 100)], "beatriz": [(330, 90)], "rafael": [(80, 90)],
          "camila": [(336, 96)], "jorge": [(326, 86)], "yasmin": [(80, 90)], "otavio": [(330, 100)]}


def avatar(p, com_objeto=True):
    objeto = (p.objeto() if com_objeto else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" role="img" aria-label="Retrato de {p.nome}">'
            f'<defs>{goiva(len(p.id))}</defs><rect width="400" height="400" fill="{TINTA}"/>'
            f'<g filter="url(#goiva-{len(p.id)})">{ceu(EVITAR[p.id])}{nuvem(p.cor)}{objeto}{p.figura(p)}</g>'
            f'{moldura()}</svg>')


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
        (0.56, 300, [("otavio", 92), ("helena", 232), ("jorge", 372), ("camila", 512)]),
        (0.7, 430, [("beatriz", 120), ("yasmin", 300), ("rafael", 480)]),
        (1.0, 590, [("davi", 300)]),
    ]
    pessoas = ""
    for escala, cy, membros in fileiras:
        for pid, cx in membros:
            p = figura[pid]
            pessoas += f'<g transform="translate({cx - 200 * escala:.1f} {cy - 190 * escala:.1f}) scale({escala})">{p.figura(p)}</g>'
    estrelas = "".join(estrela(x, y, r) if r > 4 else circulo(x, y, 2.4, PAPEL)
                       for x, y, r in [(60, 150, 8), (130, 120, 4), (200, 160, 6), (420, 130, 4), (540, 160, 8), (90, 230, 4), (500, 240, 5), (300, 140, 3), (250, 112, 4), (360, 170, 5)])
    nuvem_grupo = (f'<clipPath id="nuvem-grupo">' + "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y, r in
                   [(300, 330, 170), (120, 330, 90), (480, 330, 90), (180, 250, 80), (420, 250, 80), (300, 220, 90)]) + "</clipPath>"
                   + f'<g clip-path="url(#nuvem-grupo)"><rect width="{largura}" height="{altura}" fill="#f2c53d"/>'
                   + "".join(traco(f"M0 {y}" + "".join(f"q12 {(-3 if i % 2 else 3)} 24 0" for i in range(26)), 2.4, PAPEL) for y in range(180, 760, 12))
                   + "</g>")
    horizonte = (forma("M40 700C120 620 190 610 250 700Z", PAPEL) + coqueiro(54, 790, 150) + coqueiro(546, 790, 160, -1)
                 + forma("M488 640L494 640L497 712L485 712Z", PAPEL) + traco("M491 646L430 712M491 660L450 712M491 646L560 704", 2, PAPEL))
    titulo = (f'<rect x="60" y="34" width="480" height="64" fill="{PAPEL}"/>'
              f'<text x="300" y="82" text-anchor="middle" font-family="Alfa Slab One" font-size="44" fill="{TINTA}">PEBACAST</text>'
              + lua(520, 140, 26))
    moldura_capa = "".join(f'<rect x="{x}" y="{y}" width="12" height="12" fill="{PAPEL}"/>'
                           for i in range(0, max(largura, altura), 24)
                           for x, y in ((i, 0), (i, altura - 12), (0, i), (largura - 12, i)) if x < largura and y < altura)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" role="img" aria-label="O elenco do Pebacast">'
            f'<defs><style>{fonte_embutida("PEBACAST")}</style>{goiva(9)}</defs><rect width="{largura}" height="{altura}" fill="{TINTA}"/>'
            f'<g filter="url(#goiva-9)">{estrelas}{nuvem_grupo}{horizonte}{pessoas}</g>{titulo}'
            f'<rect width="{largura}" height="{altura}" fill="none" stroke="{TINTA}" stroke-width="24"/>{moldura_capa}'
            f'<rect x="16" y="16" width="{largura - 32}" height="{altura - 32}" fill="none" stroke="{PAPEL}" stroke-width="2.5"/></svg>')


def main():
    SAIDA.mkdir(exist_ok=True)
    pngs = []
    for p in PERSONAS:
        arquivo = SAIDA / f"{p.id}.svg"
        arquivo.write_text(avatar(p), encoding="utf-8")
        png = arquivo.with_suffix(".png")
        subprocess.run(["rsvg-convert", "-w", "600", str(arquivo), "-o", str(png)], check=True)
        pngs.append(str(png))
    subprocess.run(["montage", *pngs, "-tile", "4x2", "-geometry", "+16+16", "-background", PAPEL, str(SAIDA / "galeria.png")], check=True)
    (SAIDA / "capa-elenco.svg").write_text(capa(), encoding="utf-8")
    subprocess.run(["rsvg-convert", "-w", "900", str(SAIDA / "capa-elenco.svg"), "-o", str(SAIDA / "capa-elenco.png")], check=True)


if __name__ == "__main__":
    main()
