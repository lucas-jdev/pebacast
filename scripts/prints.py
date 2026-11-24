"""Prints de antes e depois do site, por seção (ADR 0009).

    python scripts/prints.py capturar --site <site gerado> --saida <pasta>
    python scripts/prints.py comparar <capturas antes> <capturas depois> --saida <artefato> [--pr N]
    python scripts/prints.py validar <artefato>                      (imprime o número do PR)
    python scripts/prints.py comentario <artefato> --repo dono/repo --sha <commit>

`capturar` e `comparar` rodam no workflow Capturar, sobre o código do PR, e precisam do extra
`prints` (Playwright e Pillow). `validar` e `comentario` rodam no workflow Comentar, com o código
do main e permissão de escrita, e usam só a biblioteca padrão: tudo que vem do artefato é tratado
como dado não confiável.

Regra de nome das seções: o cabeçalho (`header` fora de `section`) é `cabecalho`, o rodapé
(`footer` fora de `section`) é `rodape`, e cada `section` usa o `id`, senão o `aria-labelledby`,
senão `secao-<posição>`. O nome é normalizado para [a-z0-9-]; repetido ganha sufixo `-2`, `-3`...
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import re
import shutil
import sys
import threading
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

PAGINAS = ("index", "episodios", "sobre", "episodio")
# Como cada página aparece no comentário. "episodio" é uma página de episódio só, a primeira em ordem
# alfabética: a mesma nos dois lados da comparação, já que o PR raramente muda quais episódios existem.
ROTULOS = {"index": "index.html", "episodios": "episodios.html", "sobre": "sobre/", "episodio": "episodios/<id>/"}
TELAS = {"desktop": (1280, 900), "celular": (390, 844)}
ESTADOS = ("alterada", "nova", "removida")
SELETOR = "header, footer, section"
MARCADOR = "<!-- pebacast-prints -->"
MANIFESTO = "manifesto.json"
SEM_MUDANCA = "Nenhuma mudança visual nas páginas capturadas"

# Texto sempre em tons de cinza, sem hinting e com o glifo no pixel inteiro. No #72 o mesmo parágrafo
# saiu com antialiasing subpixel (franja colorida) num lado e em tons de cinza no outro: o Chromium
# liga ou desliga o subpixel conforme a camada em que o texto é pintado, e um PR que mexe em outra
# parte da página muda essas camadas.
ARGS_CHROMIUM = ("--disable-lcd-text", "--font-render-hinting=none", "--disable-font-subpixel-positioning")

# Comparação (ver ADR 0009). Um pixel conta como diferente quando:
# - está numa região lisa nos dois lados (nenhum canal varia mais que AMPLITUDE_LISA entre ele e os
#   8 vizinhos) e algum canal varia mais que LIMIAR_CANAL: fundo de card, faixa, área de cor;
# - ou, em qualquer lugar, a média 3x3 da diferença passa de LIMIAR_TRACO em algum canal: letra,
#   traço ou imagem que mudou.
# A seção é alterada quando mais de MAX_PIXELS_DIFERENTES pixels diferem, ou quando o tamanho muda.
# O antialiasing só redistribui a tinta entre vizinhos na borda das letras, que nunca é lisa, e a
# média 3x3 desfaz a redistribuição. Medido nas seções do #72 (subpixel contra tons de cinza): a
# regra antiga, só com LIMIAR_CANAL, marcava 21.920 pixels em index·inicio e 244.750 em
# episodios·arquivo; esta marca 0, com média 3x3 de no máximo 43, abaixo dos 48. Nos testes, uma
# palavra trocada num parágrafo dá de 229 a 620 pixels com média acima de 48 (chega a 168), e o
# fundo de um card trocado pelo tom vizinho da paleta (#efe4c8 para #f3ead2, 10 no canal que mais
# muda) dá 28 mil na região lisa. Passa o que é fino e de pouco contraste, como uma borda de 1 px.
LIMIAR_CANAL = 8
AMPLITUDE_LISA = 6
LIMIAR_TRACO = 48
MAX_PIXELS_DIFERENTES = 16
ESPERA_MS = 500

# Limites do artefato aceito pelo Comentar.
MAX_IMAGENS = 80
MAX_BYTES_IMAGEM = 8 * 1024 * 1024
MAX_BYTES_TOTAL = 64 * 1024 * 1024
MAX_BYTES_MANIFESTO = 64 * 1024
MAX_PR = 10**7

ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"
_SECAO = r"[a-z0-9]+(?:-[a-z0-9]+)*"
RE_SECAO = re.compile(rf"^{_SECAO}$")
RE_CAPTURA = re.compile(rf"^(?P<pagina>{'|'.join(PAGINAS)})--(?P<secao>{_SECAO})--(?P<tela>{'|'.join(TELAS)})\.png$")
RE_IMAGEM = re.compile(rf"^(?:{'|'.join(PAGINAS)})--{_SECAO}--(?:{'|'.join(TELAS)})--(?:antes|depois)\.png$")
RE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RE_SHA = re.compile(r"^[0-9a-f]{40}$")
TAMANHO_MAX_SECAO = 64


class ArtefatoInvalido(Exception):
    pass


# ---------------------------------------------------------------- nomes

def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:TAMANHO_MAX_SECAO].strip("-")


def nomear_secoes(elementos: Sequence[Mapping[str, Any]]) -> list[tuple[int, str]]:
    """Recebe os elementos de SELETOR na ordem do documento e devolve (índice, nome) dos que viram print."""
    nomes: list[tuple[int, str]] = []
    usados: set[str] = set()
    posicao = 0
    for elemento in elementos:
        tag = elemento["tag"]
        if tag == "section":
            posicao += 1
        if not elemento.get("visivel", True):
            continue
        if tag in ("header", "footer"):
            if elemento.get("dentro_de_secao"):
                continue
            base = "cabecalho" if tag == "header" else "rodape"
        else:
            base = normalizar(elemento.get("id") or "") or normalizar(elemento.get("rotulo") or "") or f"secao-{posicao}"
        nome, n = base, 1
        while nome in usados:
            n += 1
            nome = f"{base}-{n}"
        usados.add(nome)
        nomes.append((elemento["indice"], nome))
    return nomes


def nome_captura(pagina: str, secao: str, tela: str) -> str:
    return f"{pagina}--{secao}--{tela}.png"


def nome_imagem(item: Mapping[str, str], lado: str) -> str:
    return f"{item['pagina']}--{item['secao']}--{item['tela']}--{lado}.png"


def lados(estado: str) -> tuple[str, ...]:
    return {"alterada": ("antes", "depois"), "nova": ("depois",), "removida": ("antes",)}[estado]


# ---------------------------------------------------------------- captura (Playwright)

_JS_ELEMENTOS = """seletor => Array.from(document.querySelectorAll(seletor)).map((el, indice) => ({
  indice,
  tag: el.tagName.toLowerCase(),
  id: el.id || "",
  rotulo: el.getAttribute("aria-labelledby") || "",
  dentro_de_secao: !!(el.parentElement && el.parentElement.closest("section, article")),
  visivel: el.getClientRects().length > 0 && el.offsetWidth > 0 && el.offsetHeight > 0,
}))"""

# Cabeçalho fixo ou grudento cobriria o topo das outras seções no print. Pseudo-elemento fixo
# (a textura de papel em body::after) cairia num trecho diferente da seção conforme a rolagem,
# e mudaria o print de seções intactas sempre que a altura da página mudasse.
_JS_ESCONDER_SOBREPOSTOS = """([seletor, indice]) => {
  const alvo = document.querySelectorAll(seletor)[indice];
  const marcas = ["data-prints-oculto", "data-prints-oculto-antes", "data-prints-oculto-depois"];
  for (const marca of marcas) document.querySelectorAll(`[${marca}]`).forEach(el => el.removeAttribute(marca));
  const fixo = posicao => posicao === "fixed" || posicao === "sticky";
  for (const el of [document.body, ...document.querySelectorAll("body *")]) {
    if (fixo(getComputedStyle(el).position) && !el.contains(alvo) && !alvo.contains(el)) {
      el.setAttribute("data-prints-oculto", "");
    }
    if (fixo(getComputedStyle(el, "::before").position)) el.setAttribute("data-prints-oculto-antes", "");
    if (fixo(getComputedStyle(el, "::after").position)) el.setAttribute("data-prints-oculto-depois", "");
  }
}"""
_CSS_OCULTOS = ("[data-prints-oculto], [data-prints-oculto-antes]::before, [data-prints-oculto-depois]::after "
                "{ visibility: hidden !important; }")

# Só os pixels inteiros dentro da seção: arredondar para fora pegaria uma linha da seção vizinha,
# e qualquer mudança nela marcaria esta como alterada.
_JS_RECORTE = """([seletor, indice]) => {
  const r = document.querySelectorAll(seletor)[indice].getBoundingClientRect();
  const x = Math.ceil(r.left + window.scrollX), y = Math.ceil(r.top + window.scrollY);
  return {x, y, width: Math.floor(r.right + window.scrollX) - x, height: Math.floor(r.bottom + window.scrollY) - y};
}"""

# Imagens de fundo e máscaras (as cenas das seções) só são decodificadas quando pintadas: rolar a
# página inteira antes garante que nenhuma seção sai sem a cena por chegar antes da imagem.
# Toda espera tem teto: o evaluate do Playwright não tem timeout, e uma promessa que nunca resolve
# (um quadro que o runner não pinta, uma imagem que não decodifica) travava o job até os 20 minutos.
_JS_PREPARAR = """async ([tetoQuadroMs, tetoCargaMs]) => {
  const comTeto = (promessa, ms) => Promise.race([promessa, new Promise(ok => setTimeout(ok, ms))]);
  const quadro = () => comTeto(new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok))), tetoQuadroMs);
  document.querySelectorAll("img[loading=lazy]").forEach(img => { img.loading = "eager"; });
  await comTeto(Promise.all(Array.from(document.images).map(img => img.decode().catch(() => null))), tetoCargaMs);
  await comTeto(document.fonts.ready, tetoCargaMs);
  for (let y = 0; y < document.documentElement.scrollHeight; y += window.innerHeight) {
    window.scrollTo({top: y, behavior: "instant"});
    await quadro();
  }
  window.scrollTo({top: 0, behavior: "instant"});
  await quadro();
}"""
TETO_QUADRO_MS = 1_000
TETO_CARGA_MS = 10_000


def _servidor(site: Path):
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Silencioso(SimpleHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), partial(Silencioso, directory=str(site)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def caminho_da_pagina(site: Path, pagina: str) -> str | None:
    """Caminho relativo da página no site gerado, ou None quando ela não existe nesse lado (página nova
    ou removida pelo PR): sem arquivo não há print, e a comparação marca as seções como novas ou removidas."""
    if pagina == "episodio":
        paginas = sorted((site / "episodios").glob("*/index.html"))
        return f"{paginas[0].parent.relative_to(site).as_posix()}/" if paginas else None
    arquivo = site / (f"{pagina}/index.html" if pagina == "sobre" else f"{pagina}.html")
    return ROTULOS[pagina] if arquivo.is_file() else None


def capturar(site: Path, saida: Path, paginas: Iterable[str] = PAGINAS) -> list[Path]:
    from playwright.sync_api import sync_playwright

    saida.mkdir(parents=True, exist_ok=True)
    # Se travar, a pilha do Python vai para o stderr a cada minuto: o log do job mostra em que chamada parou.
    faulthandler.dump_traceback_later(60, repeat=True, file=sys.stderr)
    servidor = _servidor(site)
    base = f"http://127.0.0.1:{servidor.server_address[1]}/"
    gerados: list[Path] = []
    try:
        with sync_playwright() as p:
            print("abrindo o Chromium", file=sys.stderr, flush=True)
            navegador = p.chromium.launch(args=list(ARGS_CHROMIUM))
            for tela, (largura, altura) in TELAS.items():
                celular = tela == "celular"
                contexto = navegador.new_context(
                    viewport={"width": largura, "height": altura}, device_scale_factor=1,
                    is_mobile=celular, has_touch=celular, reduced_motion="reduce",
                    locale="pt-BR", timezone_id="America/Sao_Paulo",
                )
                # Votos, GoatCounter e afins variam entre execuções: fora do print.
                contexto.route("**/*", lambda rota: rota.continue_() if rota.request.url.startswith(base) else rota.abort())
                pagina_web = contexto.new_page()
                for pagina in paginas:
                    caminho = caminho_da_pagina(site, pagina)
                    if caminho is None:
                        continue
                    print(f"{tela}: carregando {caminho}", file=sys.stderr, flush=True)
                    pagina_web.goto(f"{base}{caminho}", wait_until="networkidle")
                    pagina_web.add_style_tag(content=_CSS_OCULTOS)
                    print(f"{tela}: preparando {caminho}", file=sys.stderr, flush=True)
                    pagina_web.evaluate(_JS_PREPARAR, [TETO_QUADRO_MS, TETO_CARGA_MS])
                    pagina_web.wait_for_timeout(ESPERA_MS)
                    elementos = pagina_web.evaluate(_JS_ELEMENTOS, SELETOR)
                    for indice, secao in nomear_secoes(elementos):
                        pagina_web.evaluate(_JS_ESCONDER_SOBREPOSTOS, [SELETOR, indice])
                        arquivo = saida / nome_captura(pagina, secao, tela)
                        recorte = pagina_web.evaluate(_JS_RECORTE, [SELETOR, indice])
                        if recorte["width"] <= 0 or recorte["height"] <= 0:
                            continue
                        pagina_web.screenshot(path=str(arquivo), full_page=True, clip=recorte,
                                              animations="disabled", caret="hide", scale="css")
                        gerados.append(arquivo)
                contexto.close()
            navegador.close()
    finally:
        faulthandler.cancel_dump_traceback_later()
        servidor.shutdown()
    return gerados


# ---------------------------------------------------------------- comparação

def _vizinhanca(x: Any, juntar: Callable[[Any, Any], Any]) -> Any:
    """`juntar` (np.maximum, np.minimum ou np.add) de cada pixel com os 8 vizinhos; a borda se repete."""
    import numpy as np

    p = np.pad(x, ((1, 1), (1, 1), (0, 0)), mode="edge")
    linhas = juntar(juntar(p[:, :-2], p[:, 1:-1]), p[:, 2:])
    return juntar(juntar(linhas[:-2], linhas[1:-1]), linhas[2:])


def imagens_diferentes(antes: Any, depois: Any) -> bool:
    """Tamanhos diferentes contam como mudança; senão, a regra do cabeçalho (canais de 0 a 255)."""
    import numpy as np

    a, b = np.asarray(antes), np.asarray(depois)
    if a.shape != b.shape:
        return True
    if a.ndim == 2:
        a, b = a[..., None], b[..., None]
    a, b = a.astype(np.int16), b.astype(np.int16)
    linhas, colunas = np.nonzero((np.abs(a - b) > LIMIAR_CANAL).any(axis=2))
    if not len(linhas):
        return False
    # Todo pixel que pode contar fica a até 1 px de um que passa de LIMIAR_CANAL, e a vizinhança dele
    # a até 2 px: basta esse retângulo, e a página de episódios inteira tem mais de 11 milhões de pixels.
    y0, y1 = max(linhas.min() - 2, 0), linhas.max() + 3
    x0, x1 = max(colunas.min() - 2, 0), colunas.max() + 3
    a, b = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    diferenca = a - b

    def lisa(x: Any) -> Any:
        return (_vizinhanca(x, np.maximum) - _vizinhanca(x, np.minimum)).max(axis=2) <= AMPLITUDE_LISA

    na_area_lisa = lisa(a) & lisa(b) & (np.abs(diferenca).max(axis=2) > LIMIAR_CANAL)
    no_traco = (np.abs(_vizinhanca(diferenca, np.add)) > 9 * LIMIAR_TRACO).any(axis=2)
    return int((na_area_lisa | no_traco).sum()) > MAX_PIXELS_DIFERENTES


def _carregar_png(arquivo: Path) -> Any:
    import numpy as np
    from PIL import Image

    with Image.open(arquivo) as imagem:
        return np.asarray(imagem.convert("RGBA"))


def _capturas(pasta: Path) -> dict[tuple[str, str, str], Path]:
    capturas = {}
    for arquivo in sorted(pasta.glob("*.png")):
        if m := RE_CAPTURA.match(arquivo.name):
            capturas[(m["pagina"], m["secao"], m["tela"])] = arquivo
    return capturas


def _ordem(chave: tuple[str, str, str]) -> tuple[int, int, str]:
    pagina, secao, tela = chave
    return (list(TELAS).index(tela), PAGINAS.index(pagina), secao)


def comparar(antes: Path, depois: Path, saida: Path, pr: int = 0,
             carregar: Callable[[Path], Any] = _carregar_png) -> dict[str, Any]:
    """Grava em `saida` só os pares que mudaram e o manifesto, e devolve o manifesto."""
    capturas_antes, capturas_depois = _capturas(antes), _capturas(depois)
    saida.mkdir(parents=True, exist_ok=True)
    itens = []
    for chave in sorted(capturas_antes.keys() | capturas_depois.keys(), key=_ordem):
        a, d = capturas_antes.get(chave), capturas_depois.get(chave)
        if a and d:
            if not imagens_diferentes(carregar(a), carregar(d)):
                continue
            estado = "alterada"
        else:
            estado = "nova" if d else "removida"
        pagina, secao, tela = chave
        item = {"pagina": pagina, "secao": secao, "tela": tela, "estado": estado}
        origem = {"antes": a, "depois": d}
        for lado in lados(estado):
            shutil.copyfile(origem[lado], saida / nome_imagem(item, lado))
        itens.append(item)
    manifesto = {"pr": pr, "itens": itens}
    (saida / MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifesto


# ---------------------------------------------------------------- validação (Comentar)

def _validar_item(item: Any) -> dict[str, str]:
    if not isinstance(item, dict) or set(item) != {"pagina", "secao", "tela", "estado"}:
        raise ArtefatoInvalido("item do manifesto fora do formato")
    if not all(isinstance(v, str) for v in item.values()):
        raise ArtefatoInvalido("item do manifesto com valor que não é texto")
    if item["pagina"] not in PAGINAS or item["tela"] not in TELAS or item["estado"] not in ESTADOS:
        raise ArtefatoInvalido("página, tela ou estado desconhecido no manifesto")
    if len(item["secao"]) > TAMANHO_MAX_SECAO or not RE_SECAO.match(item["secao"]):
        raise ArtefatoInvalido("nome de seção inválido no manifesto")
    return item


def validar(pasta: Path) -> dict[str, Any]:
    """Confere o artefato inteiro e devolve o manifesto; qualquer desvio recusa tudo."""
    if not pasta.is_dir() or pasta.is_symlink():
        raise ArtefatoInvalido("artefato ausente")
    imagens: dict[str, int] = {}
    manifesto_bytes: bytes | None = None
    for entrada in sorted(pasta.iterdir()):
        if entrada.is_symlink() or not entrada.is_file():
            raise ArtefatoInvalido(f"entrada que não é arquivo comum: {entrada.name!r}")
        tamanho = entrada.stat().st_size
        if entrada.name == MANIFESTO:
            if tamanho > MAX_BYTES_MANIFESTO:
                raise ArtefatoInvalido("manifesto grande demais")
            manifesto_bytes = entrada.read_bytes()
            continue
        if not RE_IMAGEM.match(entrada.name):
            raise ArtefatoInvalido(f"arquivo inesperado: {entrada.name!r}")
        if tamanho > MAX_BYTES_IMAGEM:
            raise ArtefatoInvalido(f"imagem grande demais: {entrada.name}")
        with entrada.open("rb") as f:
            cabecalho = f.read(16)
        if not (cabecalho.startswith(ASSINATURA_PNG) and cabecalho[12:16] == b"IHDR"):
            raise ArtefatoInvalido(f"não é PNG: {entrada.name}")
        imagens[entrada.name] = tamanho
    if manifesto_bytes is None:
        raise ArtefatoInvalido("manifesto ausente")
    if len(imagens) > MAX_IMAGENS:
        raise ArtefatoInvalido("imagens demais")
    if sum(imagens.values()) > MAX_BYTES_TOTAL:
        raise ArtefatoInvalido("artefato grande demais")
    try:
        manifesto = json.loads(manifesto_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise ArtefatoInvalido("manifesto não é JSON") from erro
    if not isinstance(manifesto, dict) or set(manifesto) != {"pr", "itens"}:
        raise ArtefatoInvalido("manifesto fora do formato")
    pr = manifesto["pr"]
    if type(pr) is not int or not 0 < pr < MAX_PR:
        raise ArtefatoInvalido("número do PR inválido")
    if not isinstance(manifesto["itens"], list) or len(manifesto["itens"]) > MAX_IMAGENS:
        raise ArtefatoInvalido("lista de itens inválida")
    itens = [_validar_item(item) for item in manifesto["itens"]]
    chaves = [(i["pagina"], i["secao"], i["tela"]) for i in itens]
    if len(set(chaves)) != len(chaves):
        raise ArtefatoInvalido("item repetido no manifesto")
    esperadas = {nome_imagem(item, lado) for item in itens for lado in lados(item["estado"])}
    if esperadas != set(imagens):
        raise ArtefatoInvalido("as imagens não batem com o manifesto")
    return {"pr": pr, "itens": itens}


# ---------------------------------------------------------------- comentário

def _paginas_capturadas() -> str:
    rotulos = [f"`{ROTULOS[p]}`" for p in PAGINAS]
    return ", ".join(rotulos[:-1]) + " e " + rotulos[-1]


def comentario(manifesto: Mapping[str, Any], repo: str, sha: str) -> str:
    """Markdown do comentário; recebe só manifesto já validado."""
    if not RE_REPO.match(repo) or not RE_SHA.match(sha):
        raise ValueError("repositório ou commit inválido")
    curto = sha[:7]
    base = f"https://raw.githubusercontent.com/{repo}/prints/pr-{manifesto['pr']}"
    linhas = [MARCADOR, "## Prints de antes e depois", ""]
    itens = manifesto["itens"]
    if not itens:
        linhas.append(f"{SEM_MUDANCA} ({_paginas_capturadas()}, desktop e celular), no commit `{curto}`.")
        return "\n".join(linhas) + "\n"
    linhas += [f"Seções que mudaram nas páginas capturadas ({_paginas_capturadas()}), no commit `{curto}`. "
               "Gerado pelos workflows Capturar e Comentar (ADR 0009).", ""]
    for tela, (largura, _) in TELAS.items():
        da_tela = [i for i in itens if i["tela"] == tela]
        if not da_tela:
            continue
        linhas += [f"### {tela.capitalize()} ({largura} px)", ""]
        for item in da_tela:
            def celula(lado: str) -> str:
                if lado not in lados(item["estado"]):
                    return "_seção nova_" if lado == "antes" else "_seção removida_"
                # A query muda a cada commit e fura o cache das imagens no comentário editado.
                return f"![{lado.capitalize()}: {item['secao']}]({base}/{nome_imagem(item, lado)}?v={curto})"
            linhas += [f"**{ROTULOS[item['pagina']]} · {item['secao']}** ({item['estado']})", "",
                       "| Antes | Depois |", "|---|---|", f"| {celula('antes')} | {celula('depois')} |", ""]
    return "\n".join(linhas)


# ---------------------------------------------------------------- CLI

def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prints", description="Prints de antes e depois do site, por seção.")
    sub = parser.add_subparsers(dest="comando", required=True)
    cap = sub.add_parser("capturar", help="Fotografa cada seção das páginas no desktop e no celular.")
    cap.add_argument("--site", type=Path, required=True, help="Pasta do site gerado (publicacao --site).")
    cap.add_argument("--saida", type=Path, required=True)
    comp = sub.add_parser("comparar", help="Guarda só os pares que mudaram, com o manifesto.")
    comp.add_argument("antes", type=Path)
    comp.add_argument("depois", type=Path)
    comp.add_argument("--saida", type=Path, required=True)
    comp.add_argument("--pr", type=int, default=0)
    val = sub.add_parser("validar", help="Confere o artefato e imprime o número do PR.")
    val.add_argument("artefato", type=Path)
    com = sub.add_parser("comentario", help="Imprime o comentário do PR a partir do artefato.")
    com.add_argument("artefato", type=Path)
    com.add_argument("--repo", required=True)
    com.add_argument("--sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    try:
        if args.comando == "capturar":
            for arquivo in capturar(args.site, args.saida):
                print(arquivo)
        elif args.comando == "comparar":
            manifesto = comparar(args.antes, args.depois, args.saida, args.pr)
            print(f"{len(manifesto['itens'])} seções mudaram.")
        elif args.comando == "validar":
            print(validar(args.artefato)["pr"])
        else:
            corpo = comentario(validar(args.artefato), args.repo, args.sha)
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(corpo)
    except ArtefatoInvalido as erro:
        print(f"Artefato recusado: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
