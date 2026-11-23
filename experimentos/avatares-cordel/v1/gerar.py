import base64
import io
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TINTA = "#15110c"
LADO = 400
CENTRO = (200, 185)
SAIDA = Path(__file__).parent / "svg"


@dataclass(frozen=True)
class Persona:
    id: str
    nome: str
    rotulo: str
    papel: str
    desenho: Callable[[str], str]


def circulo(x, y, r, cor=TINTA, extra=""):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{cor}" {extra}/>'


def traco(d, largura=4, cor=TINTA, extra=""):
    return f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="{largura}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'


def forma(d, cor=TINTA, extra=""):
    return f'<path d="{d}" fill="{cor}" {extra}/>'


def cortes(pontos, papel, largura=3):
    return "".join(traco(f"M{x1} {y1}L{x2} {y2}", largura, papel) for x1, y1, x2, y2 in pontos)


def moldura(papel):
    dentes = "".join(
        f'<path d="M{x} 16l8-8 8 8zM{x} 384l8 8 8-8z" fill="{papel}"/>'
        f'<path d="M16 {x}l-8 8 8 8zM384 {x}l8 8-8 8z" fill="{papel}"/>'
        for x in range(24, 376, 22)
    )
    return (
        f'<rect width="{LADO}" height="{LADO}" fill="{TINTA}"/>'
        f'<rect x="16" y="16" width="368" height="368" fill="{papel}"/>{dentes}'
        f'<rect x="24" y="24" width="352" height="352" fill="none" stroke="{TINTA}" stroke-width="2"/>'
    )


def sol(papel):
    cx, cy = CENTRO
    serra = []
    for i in range(40):
        a1, a2, am = math.tau * i / 40, math.tau * (i + 1) / 40, math.tau * (i + 0.5) / 40
        serra.append(
            f"M{cx + 128 * math.cos(a1):.1f} {cy + 128 * math.sin(a1):.1f}"
            f"L{cx + 146 * math.cos(am):.1f} {cy + 146 * math.sin(am):.1f}"
            f"L{cx + 128 * math.cos(a2):.1f} {cy + 128 * math.sin(a2):.1f}Z"
        )
    raios = "".join(
        traco(f"M{cx + 108 * math.cos(a):.1f} {cy + 108 * math.sin(a):.1f}L{cx + 120 * math.cos(a):.1f} {cy + 120 * math.sin(a):.1f}", 3)
        for a in (math.tau * (i + 0.5) / 40 for i in range(40))
    )
    return forma("".join(serra)) + f'<circle cx="{cx}" cy="{cy}" r="128" fill="{papel}" stroke="{TINTA}" stroke-width="6"/>' + raios


def faixa(persona):
    return (
        f'<rect x="78" y="318" width="244" height="48" fill="{persona.papel}" stroke="{TINTA}" stroke-width="4"/>'
        f'<path d="M78 318l-16 24 16 24zM322 318l16 24-16 24z" fill="{TINTA}"/>'
        f'<text x="200" y="345" text-anchor="middle" font-family="Alfa Slab One" font-size="25" fill="{TINTA}">{persona.nome}</text>'
        f'<text x="200" y="360" text-anchor="middle" font-family="Literata" font-weight="700" font-size="10" letter-spacing="2.4" fill="{TINTA}">{persona.rotulo}</text>'
    )


def busto(papel, gola=""):
    return (
        forma("M58 420C62 330 112 290 172 280L228 280C288 290 338 330 342 420Z")
        + cortes([(92, 340, 104, 318), (100, 352, 114, 328), (296, 318, 308, 340), (286, 328, 300, 352)], papel)
        + gola
    )


def pescoco(papel):
    return f'<path d="M178 236L178 284Q200 296 222 284L222 236Z" fill="{papel}" stroke="{TINTA}" stroke-width="4"/>' + traco("M182 262Q200 272 218 262", 3)


ROSTO = "M142 172C142 118 258 118 258 172C258 222 236 256 200 258C164 256 142 222 142 172Z"


def rosto(papel, d=ROSTO):
    orelhas = (
        f'<ellipse cx="143" cy="184" rx="10" ry="16" fill="{papel}" stroke="{TINTA}" stroke-width="4"/>'
        f'<ellipse cx="257" cy="184" rx="10" ry="16" fill="{papel}" stroke="{TINTA}" stroke-width="4"/>'
    )
    return orelhas + f'<path d="{d}" fill="{papel}" stroke="{TINTA}" stroke-width="4.5"/>'


def olhos(estilo="abertos", papel="#fff"):
    if estilo == "abertos":
        return (circulo(176, 178, 6.5) + circulo(224, 178, 6.5)
                + traco("M164 176Q176 166 188 176", 3.5) + traco("M212 176Q224 166 236 176", 3.5))
    if estilo == "calmos":
        return (forma("M164 179Q176 171 188 179Q176 184 164 179Z") + forma("M212 179Q224 171 236 179Q224 184 212 179Z")
                + traco("M163 178Q176 170 189 178", 3.5) + traco("M211 178Q224 170 237 178", 3.5))
    if estilo == "cansados":
        return (olhos("calmos") + traco("M166 189Q176 194 186 189", 2.5) + traco("M214 189Q224 194 234 189", 2.5))
    if estilo == "piscando":
        return (circulo(176, 178, 6.5) + traco("M164 176Q176 166 188 176", 3.5)
                + traco("M212 180Q224 188 236 180", 4) + traco("M236 180L241 176", 3))
    raise ValueError(estilo)


def nariz():
    return traco("M201 182L195 205Q201 211 209 205", 3.5)


def boca(estilo):
    return {
        "aberta": forma("M178 222Q200 246 222 222Q200 230 178 222Z") + traco("M178 222Q200 230 222 222", 3),
        "calorosa": traco("M180 224Q200 240 220 224", 4),
        "canto": traco("M184 228Q204 234 220 221", 4),
        "serena": traco("M186 229Q200 234 214 229", 4),
        "seca": traco("M184 230L210 230Q216 229 219 225", 4),
    }[estilo]


def sobrancelhas(d_esq, d_dir, largura=6):
    return traco(d_esq, largura) + traco(d_dir, largura)


def caneca(x, y, papel, vapor=True):
    corpo = forma(f"M{x} {y}h30v30q0 8-8 8h-14q-8 0-8-8z") + traco(f"M{x + 30} {y + 8}q12 0 12 10t-12 10", 4)
    fumaca = traco(f"M{x + 8} {y - 6}q-6-8 0-14t0-12M{x + 20} {y - 6}q-6-8 0-14t0-12", 3) if vapor else ""
    return corpo + fumaca + cortes([(x + 6, y + 8, x + 6, y + 26)], papel, 2.5)


def davi(p):
    cachos = "".join(circulo(200 + 62 * math.cos(a), 142 + 52 * math.sin(a), 13) for a in [math.pi + i * math.pi / 9 for i in range(10)])
    cabelo = forma("M140 172C132 112 172 92 200 94C230 92 270 112 260 172C250 146 230 132 200 134C170 132 150 146 140 172Z") + cachos
    fone = (traco("M134 182C130 92 270 92 266 182", 11) + traco("M134 182C130 92 270 92 266 182", 3, p)
            + '<rect x="122" y="160" width="26" height="46" rx="8" fill="#15110c"/>'
            + '<rect x="252" y="160" width="26" height="46" rx="8" fill="#15110c"/>'
            + cortes([(129, 170, 129, 196), (271, 170, 271, 196)], p, 3)
            + traco("M134 204Q146 246 180 238", 5) + circulo(184, 237, 7))
    camiseta = traco("M176 282Q200 302 224 282", 5, p) + f'<text x="200" y="318" text-anchor="middle" font-family="Alfa Slab One" font-size="22" fill="{p}">{{ }}</text>'
    caixa = (forma("M300 52h48v40h-48z") + traco("M324 52v14", 4, p) + traco("M300 66h48", 3, p)
             + traco("M314 80l6-6 6 6M320 74v12", 2.5, p))
    return (caneca(46, 58, p) + caixa + sol(p) + busto(p, camiseta) + pescoco(p) + rosto(p) + cabelo
            + sobrancelhas("M163 161Q176 151 189 158", "M211 158Q224 151 237 161") + olhos("abertos") + nariz() + boca("aberta") + fone)


def helena(p):
    cabelo_tras = forma("M200 100C150 96 122 128 128 178C120 200 138 214 126 234C116 252 134 264 122 280L172 280"
                        "C158 262 166 240 156 218C150 200 154 186 154 176Z")
    cabelo_tras += forma("M200 100C246 96 272 126 264 174L250 172Z")
    ondas = "".join(traco(d, 2.6, p) for d in ("M138 196q10 10 2 22", "M134 232q10 10 2 22", "M148 206q8 10 2 20", "M146 244q8 8 4 20"))
    franja = forma("M142 172C140 124 166 104 198 104C236 102 266 124 264 170C254 140 230 126 206 126C198 128 192 132 186 140"
                   "C178 130 172 122 170 118C158 130 148 148 142 172Z")
    mecha_grisalha = traco("M190 108C222 108 248 122 258 150", 5, p) + traco("M196 116C220 118 238 128 248 146", 2.4, p)
    lapis = (f'<g transform="rotate(-34 262 160)"><rect x="262" y="155" width="48" height="9" fill="{p}" stroke="#15110c" stroke-width="3"/>'
             f'<path d="M310 155l11 4.5-11 4.5z" fill="#15110c"/></g>')
    marcas = traco("M238 182L245 178M238 188L245 189", 2.2) + traco("M162 182L155 178", 2.2) + traco("M181 216Q176 222 178 230", 2.2)
    blazer = (forma("M182 280L200 304L218 280Z", p) + traco("M182 280L200 304L218 280", 3.5)
              + forma("M182 280L168 300L192 294Z", p) + forma("M218 280L232 300L208 294Z", p)
              + traco("M182 280L168 300L192 294M218 280L232 300L208 294", 3)
              + traco("M168 300L188 366M232 300L212 366", 4, p) + circulo(200, 336, 4, p))
    blocos = "".join(f'<rect x="{x}" y="{y}" width="22" height="16" fill="#15110c"/>' for x, y in [(38, 88), (62, 88), (50, 70), (74, 70), (62, 52)])
    blocos += cortes([(42, 96, 56, 96), (54, 78, 68, 78), (66, 60, 80, 60)], p, 2.5)
    livro = (forma("M302 50h44v52h-44z") + traco("M310 50v52", 3, p)
             + f'<text x="328" y="81" text-anchor="middle" font-family="Alfa Slab One" font-size="11" fill="{p}">ADR</text>')
    return (blocos + livro + sol(p) + cabelo_tras + ondas + busto(p, blazer) + pescoco(p) + rosto(p) + franja + mecha_grisalha + lapis + marcas
            + sobrancelhas("M163 162Q176 157 189 162", "M211 156Q224 146 238 154") + olhos("abertos") + nariz() + boca("canto"))


def beatriz(p):
    volume = "".join(circulo(200 + 78 * math.cos(a), 166 + 74 * math.sin(a), 24) for a in [math.pi * 0.8 + i * math.pi * 1.4 / 12 for i in range(13)])
    volume += circulo(200, 160, 76)
    espirais = "".join(traco(f"M{200 + 82 * math.cos(a):.0f} {166 + 78 * math.sin(a):.0f}m-6 0a6 6 0 1 1 6 6", 2.5, p) for a in [math.pi * 0.85 + i * math.pi * 1.3 / 9 for i in range(10)])
    franja = "".join(circulo(150 + i * 20, 126 + abs(i - 2.5) * 5, 14) for i in range(6))
    argolas = traco("M143 202a7 9 0 1 0 0.1 0", 3) + traco("M257 202a7 9 0 1 0 0.1 0", 3)
    blusa = forma("M172 280L200 318L228 280Z", p) + traco("M172 280L200 318L228 280", 4) + traco("M184 300Q200 318 216 300", 3, p)
    ponte = (traco("M38 96Q62 58 86 96", 5) + traco("M38 96H86", 5) + traco("M50 96V80M62 96V72M74 96V80", 3))
    pergunta = f'<text x="324" y="102" text-anchor="middle" font-family="Alfa Slab One" font-size="52" fill="#15110c">?</text>'
    return (ponte + pergunta + sol(p) + volume + espirais + busto(p, blusa) + pescoco(p) + rosto(p) + franja + argolas
            + sobrancelhas("M163 160Q176 153 189 159", "M211 159Q224 153 237 160") + olhos("abertos") + nariz() + boca("calorosa"))


def camila(p):
    rabo = forma("M232 112C292 96 318 150 300 214C296 180 282 150 252 140Z") + cortes([(262, 120, 296, 170), (270, 116, 302, 190)], p, 2.5)
    elastico = circulo(240, 112, 8) + circulo(240, 112, 3, p)
    cabelo = forma("M140 176C134 112 176 100 204 104C238 104 266 124 260 176C252 148 234 132 200 132C172 132 150 148 140 176Z")
    oculos = (f'<circle cx="176" cy="178" r="17" fill="none" stroke="#15110c" stroke-width="4"/>'
              f'<circle cx="224" cy="178" r="17" fill="none" stroke="#15110c" stroke-width="4"/>' + traco("M193 176Q200 170 207 176", 4))
    gola = forma("M170 278Q200 300 230 278L230 296Q200 316 170 296Z", p) + traco("M170 278Q200 300 230 278M170 296Q200 316 230 296", 3.5)
    gola += cortes([(182, 292, 182, 304), (194, 296, 194, 308), (206, 296, 206, 308), (218, 292, 218, 304)], "#15110c", 2.5)
    banco = (forma("M40 58a24 8 0 0 1 48 0v38a24 8 0 0 1-48 0z") + traco("M40 58a24 8 0 0 0 48 0", 3, p)
             + traco("M40 72a24 8 0 0 0 48 0M40 86a24 8 0 0 0 48 0", 2.5, p))
    etiqueta = (forma("M310 56h34v46h-34l-12-23z") + circulo(312, 79, 4, p) + traco("M300 79Q288 64 296 50", 3)
                + circulo(328, 70, 7, p) + forma("M316 98c0-14 24-14 24 0z", p))
    return (banco + etiqueta + sol(p) + rabo + elastico + busto(p, gola) + pescoco(p) + rosto(p) + cabelo
            + sobrancelhas("M162 154Q176 147 190 153", "M210 153Q224 147 238 154") + olhos("abertos") + oculos + nariz() + boca("aberta"))


def jorge(p):
    rosto_largo = "M138 170C138 116 262 116 262 170C262 222 240 258 200 260C160 258 138 222 138 170Z"
    laterais = forma("M138 182C132 150 140 132 152 126L156 168Z") + forma("M262 182C268 150 260 132 248 126L244 168Z")
    laterais += cortes([(142, 140, 148, 156), (258, 140, 252, 156)], p, 2.5)
    barba = forma("M140 186C146 236 170 270 200 272C230 270 254 236 260 186C250 206 236 214 224 214C214 206 186 206 176 214C164 214 150 206 140 186Z")
    barba += cortes([(160, 226, 166, 246), (176, 238, 180, 258), (200, 244, 200 , 264), (224, 238, 220, 258), (240, 226, 234, 246)], p, 2.5)
    bigode = traco("M184 226Q200 232 216 226", 4, p)
    rugas = traco("M176 140Q200 134 224 140", 2.5) + traco("M182 150Q200 146 218 150", 2.5)
    xadrez = cortes([(90, 300, 310, 300), (70, 340, 330, 340), (120, 286, 120, 400), (280, 286, 280, 400), (160, 282, 160, 400), (240, 282, 240, 400)], p, 2)
    cabo = traco("M110 300C140 330 170 300 200 330S260 300 290 330", 6, p) + f'<rect x="284" y="322" width="16" height="12" fill="{p}"/>'
    gola = traco("M174 280L200 304L226 280", 5, p)
    rack = (f'<rect x="40" y="46" width="44" height="56" fill="#15110c"/>'
            + "".join(f'<rect x="46" y="{y}" width="32" height="8" fill="{p}"/>' + circulo(72, y + 4, 2) for y in (52, 64, 76, 88)))
    lua = (forma("M340 52a26 26 0 1 0 0 46a20 20 0 1 1 0-46z")
           + f'<text x="342" y="86" text-anchor="middle" font-family="Alfa Slab One" font-size="15" fill="#15110c">3h</text>')
    return (rack + lua + sol(p) + busto(p, xadrez + cabo + gola) + pescoco(p) + rosto(p, rosto_largo) + laterais + rugas + barba + bigode
            + sobrancelhas("M162 162L188 160", "M212 160L238 162", 7) + olhos("calmos") + nariz())


def otavio(p):
    cabelo_branco = (forma("M143 200C138 170 142 150 154 138C158 158 160 180 158 200Z")
                     + forma("M257 200C262 170 258 150 246 138C242 158 240 180 242 200Z")
                     + cortes([(147, 160, 149, 190), (152, 152, 153, 186), (253, 160, 251, 190), (248, 152, 247, 186)], p, 2))
    calva = traco("M176 128Q186 120 196 124", 3)
    rugas = traco("M174 146Q200 140 226 146", 2.5) + traco("M180 156Q200 152 220 156", 2.5)
    vincos = traco("M180 204Q172 216 176 228", 2.5) + traco("M220 204Q228 216 224 228", 2.5)
    bigode = forma("M174 216Q200 200 226 216Q214 222 200 216Q186 222 174 216Z") + cortes([(186, 212, 190, 218), (210, 212, 214, 218)], p, 2)
    oculos = (traco("M160 184h30q0 14-15 14t-15-14z", 3.5) + traco("M210 184h30q0 14-15 14t-15-14z", 3.5) + traco("M190 184Q200 178 210 184", 3) + traco("M160 184L148 178M240 184L252 178", 3))
    paleto = (forma("M174 280L200 326L226 280Z", p) + traco("M174 280L200 326L226 280", 4)
              + forma("M193 290L207 290L204 300L210 340L200 352L190 340L196 300Z") + cortes([(196, 312, 204, 306), (195, 326, 205, 320)], p, 2)
              + traco("M174 280L150 290L182 370M226 280L250 290L218 370", 4, p))
    cidade = forma("M36 104V80h10V62h12v18h6V50h14v54zM88 104V72h8v32z") + cortes([(52, 70, 52, 76), (70, 60, 70, 66), (70, 76, 70, 82), (44, 90, 44, 96)], p, 2.5)
    rosa = (forma("M326 44L332 72L360 78L332 84L326 112L320 84L292 78L320 72Z")
            + forma("M326 66L330 78L326 90L322 78Z", p) + circulo(326, 78, 3))
    return (cidade + rosa + sol(p) + busto(p, paleto) + pescoco(p) + rosto(p) + cabelo_branco + calva + rugas + vincos
            + sobrancelhas("M160 166Q174 158 190 164", "M210 164Q226 158 240 166", 6) + olhos("calmos") + oculos + nariz() + bigode + boca("serena"))


def rafael(p):
    espetos = "M140 172C132 120 160 98 200 100C240 98 268 120 260 172C256 150 246 140 236 136L240 118L224 128L220 108L206 124L196 104L186 124L172 110L170 130L154 120L158 140C150 148 144 158 140 172Z"
    cabelo = forma(espetos)
    barba_rala = "".join(circulo(x, y, 1.8) for x, y in [(168, 220), (174, 232), (182, 242), (192, 248), (208, 248), (218, 242), (226, 232), (232, 220), (186, 236), (214, 236), (200, 242), (178, 226), (222, 226)])
    jaqueta = (forma("M168 278L184 300L200 284L216 300L232 278Z", p) + traco("M168 278L184 300L200 284L216 300L232 278", 4)
               + traco("M200 296V400", 4, p) + cortes([(194, 310, 206, 310), (194, 326, 206, 326), (194, 342, 206, 342)], p, 2))
    torre = (traco("M60 104L72 54L84 104M64 88H80M67 74H77", 4) + circulo(72, 52, 4)
             + traco("M50 54Q44 64 50 74M94 54Q100 64 94 74", 3) + traco("M88 40L100 52M100 40L88 52", 4))
    duplicada = (circulo(318, 82, 18) + circulo(334, 70, 18, extra='stroke="%s" stroke-width="3"' % p)
                 + f'<text x="334" y="77" text-anchor="middle" font-family="Alfa Slab One" font-size="17" fill="{p}">2×</text>')
    return (torre + duplicada + sol(p) + busto(p, jaqueta) + pescoco(p) + rosto(p) + cabelo + barba_rala
            + sobrancelhas("M163 164L189 162", "M211 162L237 164", 6) + olhos("cansados") + nariz() + boca("seca"))


def yasmin(p):
    chanel = forma("M136 230C126 160 140 104 200 102C260 104 274 160 264 230L250 230C254 190 248 170 240 160L160 160C152 170 146 190 150 230Z")
    chanel += cortes([(146, 180, 142, 222), (254, 180, 258, 222)], p, 2.5)
    franja = forma("M146 168C146 120 170 108 200 108C230 108 254 120 254 168L238 158L226 168L212 156L198 168L184 156L170 168L158 158Z")
    brincos = circulo(257, 202, 3) + circulo(257, 192, 2.5) + circulo(262, 176, 2.5) + traco("M143 200v10", 3) + circulo(143, 214, 4)
    capuz = (forma("M140 286C150 262 250 262 260 286C240 300 160 300 140 286Z") + traco("M150 284C170 270 230 270 250 284", 3, p)
             + traco("M182 294L178 338M218 294L222 338", 3, p) + circulo(178, 342, 4, p) + circulo(222, 342, 4, p))
    chave = (circulo(58, 62, 14) + circulo(58, 62, 6, p) + traco("M66 74L92 102M80 88L88 80M86 94L94 86", 6))
    bandeira = forma("M316 46L344 56L316 68Z") + traco("M316 44V108", 5) + cortes([(322, 52, 330, 56)], p, 2)
    return (chave + bandeira + sol(p) + chanel + busto(p, capuz) + pescoco(p) + rosto(p) + franja + brincos
            + sobrancelhas("M163 160Q176 154 189 158", "M211 156Q224 150 238 156") + olhos("piscando") + nariz() + boca("canto"))


PERSONAS = [
    Persona("davi", "Davi", "APRESENTADOR", "#f2c53d", davi),
    Persona("helena", "Helena", "SAGA SOFTWARE", "#f2a7bf", helena),
    Persona("beatriz", "Beatriz", "SAGA SOLUÇÕES", "#8ccfc0", beatriz),
    Persona("rafael", "Rafael", "SAGA SISTEMAS", "#a9c8ec", rafael),
    Persona("camila", "Camila", "SAGA DADOS", "#c6dc8e", camila),
    Persona("jorge", "Jorge", "SAGA INFRAESTRUTURA", "#d8b98a", jorge),
    Persona("yasmin", "Yasmin", "SAGA SEGURANÇA", "#f2a46b", yasmin),
    Persona("otavio", "Otávio", "SAGA CORPORATIVA", "#cdb8ea", otavio),
]


FONTES = Path(__file__).resolve().parents[3] / "site" / "fontes"
VARIANTES = {
    "completo": dict(caixa=f"0 0 {LADO} {LADO}", moldura=True, faixa=True),
    "cartao": dict(caixa=f"0 0 {LADO} {LADO}", moldura=True, faixa=False),
    "cabeca": dict(caixa="96 66 208 208", moldura=False, faixa=False),
}


def fonte_embutida(familia, arquivo, texto, extra=""):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    fonte = TTFont(FONTES / arquivo)
    recorte = subset.Subsetter()
    recorte.populate(text=texto)
    recorte.subset(fonte)
    fonte.flavor = "woff2"
    buffer = io.BytesIO()
    fonte.save(buffer)
    dados = base64.b64encode(buffer.getvalue()).decode()
    return f'@font-face{{font-family:"{familia}";{extra}src:url(data:font/woff2;base64,{dados}) format("woff2")}}'


def textos(marcacao):
    return "".join(re.findall(r"<text[^>]*>([^<]*)</text>", marcacao))


def svg(persona, variante="completo"):
    config = VARIANTES[variante]
    corpo = persona.desenho(persona.papel)
    fundo = moldura(persona.papel) if config["moldura"] else f'<rect x="-50" y="-50" width="500" height="500" fill="{persona.papel}"/>'
    rotulo = faixa(persona) if config["faixa"] else ""
    corpo_visivel = corpo if config["moldura"] else re.sub(r"<text[^>]*>[^<]*</text>", "", corpo)
    titulos = textos(corpo_visivel) + (persona.nome if rotulo else "")
    estilo = fonte_embutida("Alfa Slab One", "alfa-slab-one-latin-400-normal.woff2", titulos) if titulos else ""
    if rotulo:
        estilo += fonte_embutida("Literata", "literata-latin-700-normal.woff2", persona.rotulo, "font-weight:700;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{config["caixa"]}" role="img" aria-label="Retrato de {persona.nome}">'
        f'<defs><style>{estilo}</style><clipPath id="miolo-{persona.id}"><rect x="16" y="16" width="368" height="368"/></clipPath></defs>'
        f'{fundo}<g clip-path="url(#miolo-{persona.id})">{corpo_visivel}</g>{rotulo}</svg>'
    )


def main():
    pngs = []
    for variante in VARIANTES:
        pasta = SAIDA / variante
        pasta.mkdir(parents=True, exist_ok=True)
        for persona in PERSONAS:
            arquivo = pasta / f"{persona.id}.svg"
            arquivo.write_text(svg(persona, variante), encoding="utf-8")
            if variante == "completo":
                png = arquivo.with_suffix(".png")
                subprocess.run(["rsvg-convert", "-w", "600", str(arquivo), "-o", str(png)], check=True)
                pngs.append(str(png))
    subprocess.run(["montage", *pngs, "-tile", "4x2", "-geometry", "+16+16", "-background", "#efe4c8",
                    str(SAIDA.parent / "galeria.png")], check=True)


if __name__ == "__main__":
    main()
