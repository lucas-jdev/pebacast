"""Avisa os buscadores quando o site muda, para o Pebacast entrar no índice do Bing (ChatGPT, Copilot).

O IndexNow pede uma chave publicada no próprio site. Como o site mora numa subpasta do github.io,
a chave fica em <url_site>/<chave>.txt e vai no `keyLocation`: assim o IndexNow aceita as URLs que
estão dentro dessa subpasta, que são todas as do Pebacast.

    python -m podcast.indexacao --site _site avisar            (URLs do sitemap que mudaram há pouco)
    python -m podcast.indexacao --site _site avisar --todas    (todas as URLs do sitemap)

Avisar nunca derruba a publicação: qualquer falha vira um aviso no log e o comando sai com 0.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from podcast.roteiro import FUSO_BRASILIA, Projeto

API_INDEXNOW = "https://api.indexnow.org/indexnow"
SITEMAP = "sitemap.xml"
JANELA_PADRAO_DIAS = 2
MAX_URLS = 10_000
TEMPO_LIMITE_S = 20
_NS_SITEMAP = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# O protocolo aceita de 8 a 128 caracteres entre letras, números e hífen.
_RE_CHAVE = re.compile(r"[A-Za-z0-9-]{8,128}")

Enviar = Callable[[str, bytes], int]


def chave_indexnow(config: Mapping[str, Any]) -> str | None:
    chave = str((config.get("site") or {}).get("indexnow") or "")
    return chave if _RE_CHAVE.fullmatch(chave) else None


def escrever_chave(config: Mapping[str, Any], site: Path) -> Path | None:
    """Publica <chave>.txt com a própria chave, que é como o IndexNow confere que o site é nosso."""
    chave = chave_indexnow(config)
    if chave is None:
        return None
    arquivo = site / f"{chave}.txt"
    arquivo.write_text(chave, encoding="utf-8")
    return arquivo


def urls_para_avisar(sitemap: str, hoje: date, dias: int = JANELA_PADRAO_DIAS, todas: bool = False) -> list[str]:
    """URLs do sitemap com `lastmod` dentro da janela. Sem `lastmod`, a URL só vai com `todas`."""
    limite = hoje - timedelta(days=dias)
    urls = []
    for url in ET.fromstring(sitemap).findall("s:url", _NS_SITEMAP):
        loc = (url.findtext("s:loc", default="", namespaces=_NS_SITEMAP) or "").strip()
        lastmod = (url.findtext("s:lastmod", default="", namespaces=_NS_SITEMAP) or "").strip()
        if not loc:
            continue
        if todas or (lastmod and date.fromisoformat(lastmod[:10]) >= limite):
            urls.append(loc)
    return urls[:MAX_URLS]


def corpo_do_aviso(url_site: str, chave: str, urls: Sequence[str]) -> dict[str, Any]:
    base = url_site.rstrip("/") + "/"
    return {
        "host": urlsplit(base).hostname,
        "key": chave,
        "keyLocation": f"{base}{chave}.txt",
        "urlList": [url for url in urls if url.startswith(base)],
    }


def _enviar_por_http(url: str, corpo: bytes) -> int:
    pedido = urllib.request.Request(url, data=corpo, method="POST",
                                    headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code


def avisar(projeto: Projeto, site: Path, hoje: date | None = None, dias: int = JANELA_PADRAO_DIAS,
           todas: bool = False, enviar: Enviar = _enviar_por_http) -> str:
    """Devolve uma linha para o log. Nunca levanta exceção: o aviso é um extra da publicação."""
    config = projeto.config()
    chave = chave_indexnow(config)
    if chave is None:
        return "IndexNow: sem chave em site.indexnow, nada a avisar."
    arquivo_sitemap = site / SITEMAP
    if not arquivo_sitemap.exists():
        return f"::warning::IndexNow: {arquivo_sitemap} não existe, nada foi avisado."
    hoje = hoje or datetime.now(FUSO_BRASILIA).date()
    try:
        urls = urls_para_avisar(arquivo_sitemap.read_text(encoding="utf-8"), hoje, dias, todas)
    except (ET.ParseError, ValueError) as erro:
        return f"::warning::IndexNow: sitemap ilegível ({erro}), nada foi avisado."
    corpo = corpo_do_aviso(config["feed"]["url_site"], chave, urls)
    if not corpo["urlList"]:
        return "IndexNow: nenhuma URL mudou na janela, nada a avisar."
    try:
        status = enviar(API_INDEXNOW, json.dumps(corpo).encode("utf-8"))
    except (OSError, urllib.error.URLError) as erro:
        return f"::warning::IndexNow: falha de rede ({erro}); a publicação segue."
    lista = ", ".join(corpo["urlList"])
    if status in (200, 202):
        return f"IndexNow: {status}, {len(corpo['urlList'])} URL(s) avisada(s): {lista}"
    return f"::warning::IndexNow respondeu {status}; a publicação segue. URLs: {lista}"


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="indexacao", description="Avisa os buscadores quando o site muda.")
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--site", type=Path, default=Path("_site"), help="Site já gerado, com o sitemap.xml.")
    comandos = parser.add_subparsers(dest="comando", required=True)
    aviso = comandos.add_parser("avisar", help="Manda ao IndexNow as URLs do sitemap que mudaram.")
    aviso.add_argument("--dias", type=int, default=JANELA_PADRAO_DIAS, help="Janela do lastmod, em dias.")
    aviso.add_argument("--todas", action="store_true", help="Manda todas as URLs do sitemap.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _criar_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(avisar(Projeto(args.raiz), args.site, dias=args.dias, todas=args.todas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
