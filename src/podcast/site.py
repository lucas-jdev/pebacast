"""Páginas do Pebacast no GitHub Pages.

Gera o index.html (vitrine: último episódio e o próximo), o episodios.html (arquivo
de tudo que já foi publicado), uma página por episódio publicado em episodios/<id>/
e o sobre/ (o que é o podcast e quem faz) a partir do que está no repositório, e
copia os arquivos estáticos de site/. O feed continua saindo de podcast.publicacao.

    python -m podcast.publicacao --site _site feed
"""

import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from html import escape
from itertools import groupby
from pathlib import Path
from typing import Any

from podcast.curriculo import SAGAS
from podcast.roteiro import (
    AGUARDANDO_PUBLICACAO,
    DIAS_DA_SEMANA,
    FUSO_BRASILIA,
    Projeto,
    Proximo,
    data_de_publicacao,
    proximo_a_publicar,
)
from podcast.validacao import NOTICIA, PASTA_REVISOES, PUBLICACAO, ROTEIRO, max_revisoes

ARQUIVOS_ESTATICOS = "site"
PAGINA_EPISODIOS = "episodios.html"
PAGINA_SOBRE = "sobre/"
PASTA_DOS_EPISODIOS = "episodios"
SITEMAP = "sitemap.xml"
# Gerada de assets/og.svg por scripts/gerar_imagens.sh; o tamanho vai nas meta tags de Open Graph.
IMAGEM_COMPARTILHAMENTO = "og.jpg"
TAMANHO_DA_IMAGEM_COMPARTILHAMENTO = (1200, 630)
DESCRICAO_DA_IMAGEM = "Capa de cordel do Pebacast com o tatu-peba e a frase: cava até achar o porquê."

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")



def escrever_pagina(projeto: Projeto, site: Path, arquivo_feed: str) -> None:
    estaticos = projeto.raiz / ARQUIVOS_ESTATICOS
    if estaticos.is_dir():
        shutil.copytree(estaticos, site, dirs_exist_ok=True)
    (site / "index.html").write_text(gerar_index(projeto, arquivo_feed), encoding="utf-8")
    (site / PAGINA_EPISODIOS).write_text(gerar_pagina_episodios(projeto, arquivo_feed), encoding="utf-8")
    (site / PAGINA_SOBRE).mkdir(exist_ok=True)
    (site / PAGINA_SOBRE / "index.html").write_text(gerar_pagina_sobre(projeto, arquivo_feed), encoding="utf-8")
    for item in _publicados(projeto):
        pasta = site / caminho_do_episodio(item["episodio"]["id"])
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "index.html").write_text(
            gerar_pagina_do_episodio(projeto, arquivo_feed, item["episodio"]["id"]), encoding="utf-8")
    (site / SITEMAP).write_text(gerar_sitemap(projeto), encoding="utf-8")


def caminho_do_episodio(episodio_id: str) -> str:
    """URL permanente do episódio, relativa ao url_site: não muda nunca (ADR 0010)."""
    return f"{PASTA_DOS_EPISODIOS}/{episodio_id}/"


def gerar_index(projeto: Projeto, arquivo_feed: str, data: date | None = None) -> str:
    config = projeto.config()
    meta = config["feed"]
    sagas = projeto.sagas()
    personas = projeto.personas()
    publicados = _publicados(projeto)
    ultimo = publicados[0] if publicados else None
    proximo = proximo_a_publicar(projeto, data or data_de_publicacao())

    secoes = [
        _hero(ultimo),
        _faixa(),
        _secao_ultimo(ultimo, personas, total_publicados=len(publicados), votos=_config_do_site(config)["votos"]),
        _secao_proximo(proximo, config),
        _secao_vozes(personas),
        _secao_sagas(sagas, publicados),
        _secao_como(config),
        _secao_assinar(_url_feed(meta, arquivo_feed), meta),
    ]
    return _documento(
        config, arquivo_feed,
        titulo=f"{meta['titulo']} · arquitetura, um porquê por dia",
        descricao=_config_do_site(config)["descricao"],
        url=meta["url_site"],
        estaticos=projeto.raiz / ARQUIVOS_ESTATICOS,
        dados_estruturados=_serie(config, arquivo_feed),
        pular_para="episodios",
        cabecalho=_cabecalho(meta, atual="inicio"),
        conteudo="\n".join(s for s in secoes if s),
    )


def gerar_pagina_episodios(projeto: Projeto, arquivo_feed: str) -> str:
    config = projeto.config()
    meta = config["feed"]
    publicados = _publicados(projeto)
    serie = _serie(config, arquivo_feed)
    serie["episode"] = [_episodio_estruturado(item, meta, serie["@id"]) for item in publicados]
    return _documento(
        config, arquivo_feed,
        titulo=f"Episódios · {meta['titulo']}",
        descricao=f"Todos os episódios do {meta['titulo']}, do mais recente ao mais antigo, com áudio, desafio, transcrição e fontes.",
        url=_url(meta, PAGINA_EPISODIOS),
        estaticos=projeto.raiz / ARQUIVOS_ESTATICOS,
        dados_estruturados=serie,
        pular_para="arquivo",
        cabecalho=_cabecalho(meta, atual="episodios"),
        conteudo=_secao_arquivo(publicados, projeto.personas(), votos=_config_do_site(config)["votos"]),
    )


def gerar_pagina_sobre(projeto: Projeto, arquivo_feed: str) -> str:
    """O que é o podcast e quem faz, em texto corrido: é a página que uma IA cita para responder isso."""
    config = projeto.config()
    meta = config["feed"]
    url = _url(meta, PAGINA_SOBRE)
    serie = _serie(config, arquivo_feed)
    del serie["@context"]
    sobre = {
        "@context": "https://schema.org",
        "@type": "AboutPage",
        "@id": f"{url}#pagina",
        "url": url,
        "name": f"Sobre o {meta['titulo']}",
        "inLanguage": "pt-BR",
        "mainEntity": serie,
    }
    criador = _criador(config)
    return _documento(
        config, arquivo_feed,
        titulo=f"Sobre o {meta['titulo']} · o que é e quem faz",
        descricao=(f"O {meta['titulo']} é um podcast diário de arquitetura de software em português, "
                   f"criado por {criador['name']}. A proposta, como é feito e quem faz."),
        url=url,
        estaticos=projeto.raiz / ARQUIVOS_ESTATICOS,
        dados_estruturados=sobre,
        pular_para="sobre",
        pular_texto="Pular para o conteúdo",
        raiz="../",
        cabecalho=_cabecalho(meta, atual="sobre", raiz="../"),
        conteudo="\n".join([
            _sobre_definicao(meta, criador["name"]),
            _sobre_proposta(),
            _sobre_como(meta, _primeiro_nome(config)),
            _sobre_quem_faz(_config_do_site(config)["criador"]),
            _sobre_nome(meta),
        ]),
    )


def gerar_pagina_do_episodio(projeto: Projeto, arquivo_feed: str, episodio_id: str) -> str:
    """Página de um episódio publicado, com URL própria: é o endereço que buscadores e IAs citam."""
    config = projeto.config()
    meta = config["feed"]
    publicados = _publicados(projeto)
    item = next(i for i in publicados if i["episodio"]["id"] == episodio_id)
    episodio, saga = item["episodio"], item["saga"]
    url = _url(meta, caminho_do_episodio(episodio_id))
    serie = _serie(config, arquivo_feed)
    del serie["@context"]
    dados = {
        "@context": "https://schema.org",
        **_episodio_estruturado(item, meta, serie["@id"]),
        "partOfSeries": serie,
        "author": serie["author"],
        "inLanguage": "pt-BR",
    }
    fontes = item["roteiro"].get("fontes", [])
    if fontes:
        dados["citation"] = [{"@type": "CreativeWork", "name": fonte} for fonte in fontes]
    return _documento(
        config, arquivo_feed,
        titulo=f"{episodio['titulo']} · {saga.rotulo_do(episodio_id)} · {meta['titulo']}",
        descricao=_resumo(episodio, meta["titulo"]),
        url=url,
        estaticos=projeto.raiz / ARQUIVOS_ESTATICOS,
        dados_estruturados=dados,
        pular_para="episodio",
        pular_texto="Pular para o episódio",
        raiz="../../",
        cabecalho=_cabecalho(meta, atual="episodio", raiz="../../"),
        conteudo=_secao_do_episodio(item, publicados, projeto.personas(), _config_do_site(config)["votos"]),
    )


def _resumo(episodio: Mapping[str, Any], nome: str, limite: int = 155) -> str:
    """Descrição para buscadores: os objetivos do episódio, cortados numa palavra até o limite."""
    texto = " ".join(" ".join(episodio.get("objetivos", [])).split()) or f"Episódio do {nome}."
    if len(texto) <= limite:
        return texto
    return texto[: limite - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def _vizinhos(item: Mapping[str, Any], publicados: Sequence[Mapping[str, Any]]) -> tuple[Any, Any]:
    """O anterior e o próximo publicados da mesma saga, na ordem do currículo."""
    saga = item["saga"]
    no_ar = {i["episodio"]["id"]: i for i in publicados if i["saga"].id == saga.id}
    ordem = [e.id for e in saga.episodios if e.id in no_ar]
    posicao = ordem.index(item["episodio"]["id"])
    anterior = no_ar[ordem[posicao - 1]] if posicao > 0 else None
    proximo = no_ar[ordem[posicao + 1]] if posicao + 1 < len(ordem) else None
    return anterior, proximo


def _secao_do_episodio(item: Mapping[str, Any], publicados: Sequence[Mapping[str, Any]],
                       personas: Mapping[str, Any], votos: str) -> str:
    episodio, saga = item["episodio"], item["saga"]
    anterior, proximo = _vizinhos(item, publicados)

    def vizinho(outro: Mapping[str, Any] | None, rotulo: str, classe: str) -> str:
        if outro is None:
            return ""
        return (f'<a class="vizinhos__link vizinhos__link--{classe}" href="../../{caminho_do_episodio(outro["episodio"]["id"])}">'
                f'<span class="vizinhos__rotulo">{rotulo}</span>{escape(outro["episodio"]["titulo"])}</a>')

    links = vizinho(anterior, "← Anterior", "anterior") + vizinho(proximo, "Próximo →", "proximo")
    navegacao = (f'<nav class="vizinhos" aria-label="Outros episódios da saga {escape(saga.nome_curto)}">{links}</nav>'
                 if links else "")
    return f"""<section class="secao" id="episodio">
  <div class="largura">
    <p class="voltar"><a href="../../{PAGINA_EPISODIOS}?saga={escape(saga.id)}">← Episódios da saga {escape(saga.nome_curto)}</a></p>
    {_episodio_destaque(item, personas, votos, na_propria_pagina=True)}
    {navegacao}
  </div>
</section>"""


def gerar_sitemap(projeto: Projeto) -> str:
    meta = projeto.config()["feed"]
    publicados = _publicados(projeto)
    ultima = (f"<lastmod>{_data_iso(publicados[0]['publicacao']['publicado_em'])}</lastmod>" if publicados else "")
    urls = "".join(f"<url><loc>{escape(_url(meta, caminho))}</loc>{ultima}</url>" for caminho in ("", PAGINA_EPISODIOS))
    urls += f"<url><loc>{escape(_url(meta, PAGINA_SOBRE))}</loc></url>"
    urls += "".join(
        f"<url><loc>{escape(_url(meta, caminho_do_episodio(item['episodio']['id'])))}</loc>"
        f"<lastmod>{_data_iso(item['publicacao']['publicado_em'])}</lastmod></url>"
        for item in publicados
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')


def _config_do_site(config: Mapping[str, Any]) -> dict[str, Any]:
    site = config.get("site") or {}
    descricao = site.get("descricao") or config["feed"]["descricao"]
    return {
        "descricao": " ".join(descricao.split()),
        "imagem": site.get("imagem_compartilhamento") or IMAGEM_COMPARTILHAMENTO,
        "goatcounter": site.get("goatcounter") or "",
        "votos": _api_de_votos(site.get("votos_api") or ""),
        "criador": _config_do_criador(site.get("criador") or {}, config["feed"]["autor"]),
    }


def _config_do_criador(criador: Mapping[str, Any], autor: str) -> dict[str, Any]:
    """Quem faz o podcast. Só entra o que está na configuração: sem bio, a página não inventa uma."""
    links = [
        {"rotulo": str(link.get("rotulo") or ""), "url": str(link["url"]).rstrip("/")}
        for link in criador.get("links") or []
        if isinstance(link, Mapping) and _link_seguro(str(link.get("url") or ""))
    ]
    return {
        "nome": " ".join(str(criador.get("nome") or autor).split()),
        "papel": " ".join(str(criador.get("papel") or "").split()),
        "cidade": " ".join(str(criador.get("cidade") or "").split()),
        "bio": " ".join(str(criador.get("bio") or "").split()),
        "foto": foto if re.fullmatch(r"[a-z0-9_-]+\.(?:jpg|jpeg|png|webp)", foto := str(criador.get("foto") or "")) else "",
        "links": links,
    }


def _link_seguro(url: str) -> bool:
    """O link vai parar num href e no sameAs: só https, sem aspas nem espaço que fechem o atributo."""
    return re.fullmatch(r"https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~%-]*)*/?", url) is not None


def _api_de_votos(url: str) -> str:
    """Só aceita https num host simples: o endereço vai parar num atributo do HTML e no fetch do navegador."""
    url = url.rstrip("/")
    return url if re.fullmatch(r"https://[a-z0-9.-]+(?:/[a-z0-9._-]+)*", url) else ""


def _serie(config: Mapping[str, Any], arquivo_feed: str) -> dict[str, Any]:
    meta = config["feed"]
    return {
        "@context": "https://schema.org",
        "@type": "PodcastSeries",
        "@id": _url(meta, "#podcast"),
        "name": meta["titulo"],
        "description": " ".join(meta["descricao"].split()),
        "url": meta["url_site"],
        "webFeed": _url_feed(meta, arquivo_feed),
        "image": _url(meta, meta["capa"]),
        "inLanguage": "pt-BR",
        "author": _criador(config),
    }


def _criador(config: Mapping[str, Any]) -> dict[str, Any]:
    """A mesma Person, com o mesmo @id, em toda página: é o que liga o podcast a quem o faz."""
    meta = config["feed"]
    criador = _config_do_site(config)["criador"]
    pessoa: dict[str, Any] = {
        "@type": "Person",
        "@id": _url(meta, f"{PAGINA_SOBRE}#criador"),
        "name": criador["nome"],
        "url": _url(meta, PAGINA_SOBRE),
    }
    if criador["papel"]:
        pessoa["jobTitle"] = criador["papel"]
    if criador["cidade"]:
        pessoa["homeLocation"] = {"@type": "Place", "name": criador["cidade"]}
    if criador["foto"]:
        pessoa["image"] = _url(meta, criador["foto"])
    if criador["links"]:
        pessoa["sameAs"] = [link["url"] for link in criador["links"]]
    return pessoa


def _episodio_estruturado(item: Mapping[str, Any], meta: Mapping[str, Any], serie: str) -> dict[str, Any]:
    episodio, publicacao = item["episodio"], item["publicacao"]
    return {
        "@type": "PodcastEpisode",
        "name": episodio["titulo"],
        "url": _url(meta, caminho_do_episodio(episodio["id"])),
        "datePublished": publicacao["publicado_em"],
        "timeRequired": f"PT{max(1, round(publicacao['duracao_segundos'] / 60))}M",
        "description": " ".join(episodio.get("objetivos", [])),
        "associatedMedia": {"@type": "MediaObject", "contentUrl": publicacao["url_audio"]},
        "partOfSeries": {"@id": serie},
    }


def _json_ld(dados: Mapping[str, Any]) -> str:
    """JSON dentro de <script>: escapa o < para nenhum texto do conteúdo fechar a tag antes da hora."""
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _analytics(codigo: str) -> str:
    """GoatCounter: sem cookie e sem dado pessoal, então dispensa banner de consentimento. Sem código, nada é carregado."""
    if not re.fullmatch(r"[a-z0-9-]+", codigo):
        return ""
    return f'<script data-goatcounter="https://{codigo}.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'


# Verificação de dono no Search Console (Gemini, AI Overviews) e no Bing Webmaster Tools (ChatGPT,
# Copilot). Numa subpasta do github.io não dá para pôr arquivo na raiz do domínio, então vai por meta tag.
_VERIFICACOES = {"google": "google-site-verification", "bing": "msvalidate.01"}


def _verificacao(config: Mapping[str, Any]) -> str:
    codigos = (config.get("site") or {}).get("verificacao") or {}
    return "".join(
        f'<meta name="{nome}" content="{codigo}">\n'
        for chave, nome in _VERIFICACOES.items()
        if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", codigo := str(codigos.get(chave) or ""))
    )


def _url(meta: Mapping[str, Any], caminho: str) -> str:
    return meta["url_site"].rstrip("/") + "/" + caminho


def _versionada(url: str, arquivo: Path) -> str:
    """Põe um hash curto do conteúdo na URL: quando a imagem muda, redes sociais e apps buscam a nova em vez do cache."""
    if not arquivo.exists():
        return url
    return f"{url}?v={hashlib.sha256(arquivo.read_bytes()).hexdigest()[:8]}"


def _documento(config: Mapping[str, Any], arquivo_feed: str, *, titulo: str, descricao: str, url: str, estaticos: Path,
               dados_estruturados: Mapping[str, Any], pular_para: str, cabecalho: str, conteudo: str,
               pular_texto: str = "Pular para os episódios", raiz: str = "") -> str:
    """`raiz` leva das páginas em subpasta (sobre/) aos arquivos da raiz do site: CSS, JS, fontes e ícones."""
    meta = config["feed"]
    site = _config_do_site(config)
    largura, altura = TAMANHO_DA_IMAGEM_COMPARTILHAMENTO
    return _PAGINA.format(
        titulo=escape(titulo),
        nome=escape(meta["titulo"]),
        autor=escape(meta["autor"]),
        descricao=escape(descricao),
        url=escape(url),
        url_feed=escape(_url_feed(meta, arquivo_feed)),
        imagem=escape(_versionada(_url(meta, site["imagem"]), estaticos / site["imagem"])),
        imagem_largura=largura,
        imagem_altura=altura,
        imagem_descricao=escape(DESCRICAO_DA_IMAGEM),
        dados_estruturados=_json_ld(dados_estruturados),
        analytics=_analytics(site["goatcounter"]),
        verificacao=_verificacao(config),
        simbolos=_SIMBOLOS,
        pular_para=pular_para,
        pular_texto=escape(pular_texto),
        raiz=raiz,
        cabecalho=cabecalho,
        conteudo=conteudo,
        rodape=_rodape(meta, config, raiz),
    )


def _url_feed(meta: Mapping[str, Any], arquivo_feed: str) -> str:
    return _url(meta, arquivo_feed)


# ---------------------------------------------------------------- dados


def _publicados(projeto: Projeto) -> list[dict[str, Any]]:
    repositorio = projeto.config()["feed"]["url_repositorio"].rstrip("/")
    itens = []
    for saga in projeto.sagas().values():
        for episodio in saga.episodios:
            pasta = projeto.episodios / episodio.id
            if not (pasta / PUBLICACAO).exists():
                continue
            revisoes = sorted((pasta / PASTA_REVISOES).glob("*.json"), key=lambda a: int(a.stem))
            itens.append({
                "saga": saga,
                "episodio": episodio.dados,
                "publicacao": _ler_json(pasta / PUBLICACAO),
                "roteiro": _ler_json(pasta / ROTEIRO),
                "noticia": _ler_json(pasta / NOTICIA) if (pasta / NOTICIA).exists() else {},
                "revisoes": [_ler_json(arquivo) for arquivo in revisoes],
                "relatorio": (f"{repositorio}/blob/main/{pasta.relative_to(projeto.raiz).as_posix()}/"
                              f"{PASTA_REVISOES}/{revisoes[-1].name}" if revisoes else ""),
            })
    itens.sort(key=lambda item: item["publicacao"]["publicado_em"], reverse=True)
    return itens


def _ler_json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _data_por_extenso(iso: str) -> str:
    data = datetime.fromisoformat(iso).astimezone(FUSO_BRASILIA)
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


def _data_iso(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(FUSO_BRASILIA).date().isoformat()


def _mes_por_extenso(iso: str) -> str:
    data = datetime.fromisoformat(iso).astimezone(FUSO_BRASILIA)
    return f"{MESES[data.month - 1].capitalize()} de {data.year}"


def _duracao(segundos: int) -> str:
    return f"{segundos // 60}:{segundos % 60:02d}"


def _minutos(segundos: int) -> str:
    return f"{round(segundos / 60)} min"


def _codigo(episodio_id: str) -> str:
    """O id do episódio na capa: a sigla da saga sobre o número, para "001" nunca aparecer sozinho."""
    sigla, numero = episodio_id.upper().rsplit("-", 1)
    return f'<span class="codigo__sigla">{escape(sigla)}</span>{escape(numero)}'


# ---------------------------------------------------------------- seções


def _cabecalho(meta: Mapping[str, Any], atual: str, raiz: str = "") -> str:
    """`atual` é a página aberta ("inicio", "episodios" ou "sobre"): ganha aria-current e, na inicial, as
    âncoras ficam na própria página."""
    inicial = "" if atual == "inicio" else (raiz or "./")

    def corrente(pagina: str) -> str:
        return ' aria-current="page"' if atual == pagina else ""

    return f"""<header class="topo">
  <div class="largura topo__linha">
    <a class="marca" href="{inicial}#inicio" aria-label="{escape(meta['titulo'])}, início">
      <svg class="marca__peba" viewBox="0 0 128 80" aria-hidden="true"><use href="#peba"/></svg>
      <span class="marca__nome">{escape(meta['titulo'])}</span>
    </a>
    <nav class="topo__nav" aria-label="Seções">
      <a href="{raiz}{PAGINA_EPISODIOS}"{corrente("episodios")}>Episódios</a>
      <a href="{inicial}#sagas">Sagas</a>
      <a href="{inicial}#como">Como funciona</a>
      <a href="{raiz}{PAGINA_SOBRE}"{corrente("sobre")}>Sobre</a>
      <a class="botao botao--pequeno" href="{inicial}#assinar">Assinar</a>
    </nav>
  </div>
</header>"""


def _hero(ultimo: Mapping[str, Any] | None) -> str:
    acao = (
        '<a class="botao" href="#episodios"><svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-play"/></svg>'
        "Ouvir o último episódio</a>"
        if ultimo else '<a class="botao" href="#sagas">Ver o que vem por aí</a>'
    )
    return f"""<section class="hero" id="inicio">
  <div class="largura hero__grade">
    <div class="hero__texto">
      <p class="sobretitulo">Podcast diário de arquitetura</p>
      <h1>Cava até achar o <em>porquê</em>.</h1>
      <p class="hero__lead">Uma conversa de 15 a 20 minutos por dia sobre como sistemas são pensados.
        Cada episódio parte de um caso (real quando há notícia boa, hipotético e avisado quando não há),
        pesa os trade-offs sem torcida e termina com um desafio pra você levar pro trabalho.</p>
      <div class="hero__acoes">
        {acao}
        <a class="botao botao--contorno" href="#assinar">Assinar o feed</a>
      </div>
    </div>
    {_ILUSTRACAO_TOCA}
  </div>
</section>"""


def _faixa() -> str:
    return '<div class="faixa" role="presentation"></div>'


def _secao_ultimo(item: Mapping[str, Any] | None, personas: Mapping[str, Any], total_publicados: int, votos: str = "") -> str:
    if item is None:
        return """<section class="secao" id="episodios">
  <div class="largura"><h2 class="secao__titulo">Episódios</h2>
  <p class="vazio">O primeiro episódio está sendo cavado. Assine o feed pra receber assim que sair.</p></div>
</section>"""
    arquivo = ""
    if total_publicados > 1:
        arquivo = (f'<p class="chamada-arquivo"><a class="botao botao--contorno" href="{PAGINA_EPISODIOS}">'
                   f"Ver os {total_publicados} episódios publicados</a></p>")
    return f"""<section class="secao" id="episodios">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Episódio mais recente</p>
      <h2 class="secao__titulo">Pra ouvir agora</h2>
    </div>
    {_episodio_destaque(item, personas, votos)}
    {arquivo}
  </div>
</section>"""


def _episodio_destaque(item: Mapping[str, Any], personas: Mapping[str, Any], votos: str = "",
                       na_propria_pagina: bool = False) -> str:
    """O card grande do episódio. Na página dele, o título é o h1 e não é link (já se está lá)."""
    episodio, roteiro, saga = item["episodio"], item["roteiro"], item["saga"]
    eid = escape(episodio["id"])
    link = "./" if na_propria_pagina else caminho_do_episodio(episodio["id"])
    titulo = (f'<h1 class="episodio__titulo">{escape(episodio["titulo"])}</h1>' if na_propria_pagina else
              f'<h3 class="episodio__titulo"><a href="{escape(link)}">{escape(episodio["titulo"])}</a></h3>')
    return f"""<article class="episodio episodio--destaque" id="{eid}" data-saga="{escape(saga.id)}">
  {_etiqueta(saga, episodio["id"])}
  <div class="episodio__capa" aria-hidden="true">
    <span class="episodio__codigo">{_codigo(episodio['id'])}</span>
    <svg class="episodio__peba" viewBox="0 0 128 80"><use href="#peba"/></svg>
  </div>
  <div class="episodio__corpo">
    {_meta(item)}
    {titulo}
    {_caso(item["noticia"])}
    {_player(item["publicacao"], episodio["id"])}{_votos(episodio["id"], votos)}
    {_objetivos_e_desafio(episodio, roteiro)}
    {_selo(item)}
    {_dobra_transcricao(roteiro, personas)}
    <details class="dobra">
      <summary>Fontes</summary>
      {_fontes(roteiro)}
    </details>
    {_links(item, link)}
  </div>
</article>"""


def _secao_arquivo(publicados: Sequence[Mapping[str, Any]], personas: Mapping[str, Any], votos: str = "") -> str:
    total = len(publicados)
    if not publicados:
        lead = "Nenhum episódio publicado ainda. O primeiro está sendo cavado."
    elif total == 1:
        lead = "1 episódio publicado, com áudio, desafio, transcrição e fontes."
    else:
        lead = f"{total} episódios publicados, do mais recente ao mais antigo, com áudio, desafio, transcrição e fontes."
    meses = groupby(publicados, key=lambda item: _mes_por_extenso(item["publicacao"]["publicado_em"]))
    grupos = "\n".join(
        f"""<section class="mes" aria-labelledby="mes-{indice}">
  <h2 class="mes__titulo" id="mes-{indice}">{escape(mes)}</h2>
  <ol class="mes__lista">{''.join(_episodio_compacto(item, personas, votos) for item in itens)}</ol>
</section>"""
        for indice, (mes, itens) in enumerate(meses, start=1)
    )
    return f"""<section class="secao" id="arquivo">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Arquivo</p>
      <h1 class="secao__titulo">Todos os episódios</h1>
      <p class="secao__lead">{escape(lead)}</p>
    </div>
    {_filtro_por_saga(publicados)}
    <div class="arquivo">{grupos}</div>
  </div>
</section>"""


def _filtro_por_saga(publicados: Sequence[Mapping[str, Any]]) -> str:
    """Só aparece com duas sagas ou mais, e só com JS (classe .js no <html>), já que sem JS não filtra nada."""
    contagem: dict[str, int] = {}
    for item in publicados:
        contagem[item["saga"].id] = contagem.get(item["saga"].id, 0) + 1
    if len(contagem) < 2:
        return ""
    opcoes = [("", "Todas", len(publicados))] + [
        (sid, nome, contagem[sid]) for sid, nome, _ in SAGAS if sid in contagem
    ]
    botoes = "".join(
        f'<button class="filtro__opcao" type="button" data-saga="{escape(sid)}" aria-pressed="{"true" if not sid else "false"}">'
        f'{escape(nome)} <span class="filtro__total">{quantos}</span></button>'
        for sid, nome, quantos in opcoes
    )
    return f"""<div class="filtro" role="group" aria-label="Filtrar por saga">{botoes}
  <p class="so-leitor" role="status" data-filtro-status></p>
</div>"""


def _episodio_compacto(item: Mapping[str, Any], personas: Mapping[str, Any], votos: str = "") -> str:
    episodio, roteiro, saga = item["episodio"], item["roteiro"], item["saga"]
    eid = escape(episodio["id"])
    return f"""<li class="item" id="{eid}" data-saga="{escape(saga.id)}">
  {_etiqueta(saga, episodio["id"])}
  <div class="item__capa" aria-hidden="true">
    <span class="item__codigo">{_codigo(episodio['id'])}</span>
  </div>
  <article class="item__corpo" aria-labelledby="titulo-{eid}">
    {_meta(item)}
    <h3 class="item__titulo" id="titulo-{eid}"><a href="{escape(caminho_do_episodio(episodio['id']))}">{escape(episodio['titulo'])}</a></h3>
    {_caso(item["noticia"])}
    {_player(item["publicacao"], episodio["id"])}{_votos(episodio["id"], votos)}
    <details class="dobra">
      <summary>Objetivos e desafio</summary>
      {_objetivos_e_desafio(episodio, roteiro)}
    </details>
    {_dobra_transcricao(roteiro, personas)}
    <details class="dobra">
      <summary>Fontes</summary>
      {_selo(item)}
      {_fontes(roteiro)}
    </details>
    {_links(item, caminho_do_episodio(episodio["id"]))}
  </article>
</li>"""


def _meta(item: Mapping[str, Any]) -> str:
    publicacao = item["publicacao"]
    return f"""<p class="episodio__meta">
      <time datetime="{escape(publicacao['publicado_em'])}">{escape(_data_por_extenso(publicacao['publicado_em']))}</time>
      <span aria-hidden="true">·</span> {escape(_minutos(publicacao['duracao_segundos']))}
    </p>"""


def _etiqueta(saga: Any, episodio_id: str) -> str:
    """Etiqueta da saga amarrada ao card. O cordão é o mesmo em todo card e vem dos SVGs de site/."""
    posicao = f"{saga.posicao_do(episodio_id)} de {len(saga.episodios)}"
    return (f'<p class="etiqueta"><span class="etiqueta__papel">Saga {escape(saga.nome_curto)}'
            f'<span class="etiqueta__posicao">· <span class="etiqueta__longo">episódio</span>'
            f'<span class="etiqueta__curto">ep.</span> {posicao}</span></span></p>'
            '<span class="amarracao" aria-hidden="true"></span>'
            '<span class="amarracao amarracao--verso" aria-hidden="true"></span>')


def _caso(noticia: Mapping[str, Any]) -> str:
    if noticia.get("tipo") == "noticia":
        return (f'<p class="caso"><span class="caso__rotulo">Ponto de partida</span>'
                f'<a href="{escape(noticia["url"])}" rel="noopener">{escape(noticia["titulo"])}</a>'
                f' <span class="caso__fonte">{escape(noticia["fonte"])}</span></p>')
    cenario = _primeira_frase(noticia.get("cenario", ""))
    if not cenario:
        return ""
    return (f'<p class="caso"><span class="caso__rotulo">Ponto de partida · cenário hipotético</span>'
            f"{escape(cenario)}</p>")


def _primeira_frase(texto: str, limite: int = 180) -> str:
    """A primeira frase do cenário, que basta para o ouvinte saber de onde a conversa parte."""
    texto = " ".join(texto.split())
    frase = re.match(r".+?[.!?](?=\s|$)", texto)
    frase = frase.group(0) if frase else texto
    if len(frase) <= limite:
        return frase
    return frase[: limite - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _player(publicacao: Mapping[str, Any], episodio_id: str) -> str:
    duracao = publicacao["duracao_segundos"]
    return f"""<div class="player" data-duracao="{duracao}" data-episodio="{escape(episodio_id)}">
      <audio controls preload="none"><source src="{escape(publicacao['url_audio'])}" type="audio/mpeg"></audio>
      <button class="player__play" type="button" aria-label="Tocar">
        <svg class="player__icone-play" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-play"/></svg>
        <svg class="player__icone-pausa" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-pause"/></svg>
      </button>
      <div class="player__trilha">
        <input class="player__barra" type="range" min="0" max="{duracao}" value="0" step="1" aria-label="Posição no episódio">
        <div class="player__tempos"><span class="player__atual">0:00</span><span><span class="so-leitor">de </span>{escape(_duracao(duracao))}</span></div>
      </div>
      <button class="player__velocidade" type="button"><span class="so-leitor">Velocidade de reprodução: </span><span class="player__velocidade-valor">1×</span></button>
    </div>"""


def _votos(episodio_id: str, api: str) -> str:
    """Curti / não curti. Sem API configurada, nada aparece; sem JS, o CSS esconde (o voto depende do fetch)."""
    if not api:
        return ""
    eid = escape(episodio_id)
    opcoes = "".join(
        f'''<button class="votos__opcao" type="button" data-voto="{voto}" aria-pressed="false">'''
        f'''<svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-{voto}"/></svg>{rotulo}</button>'''
        for voto, rotulo in (("curti", "Curti"), ("nao_curti", "Não curti"))
    )
    return f"""
    <div class="votos" role="group" aria-labelledby="votos-{eid}" data-episodio="{eid}" data-api="{escape(api)}">
      <p class="votos__pergunta" id="votos-{eid}">Curtiu o episódio?</p>{opcoes}
      <form class="recado" data-recado hidden>
        <label class="recado__rotulo" for="recado-{eid}">Quer contar o porquê? <span>Opcional, vai só pra quem faz o podcast.</span></label>
        <textarea class="recado__texto" id="recado-{eid}" name="texto" rows="3" minlength="3" maxlength="1000" required></textarea>
        <div class="recado__isca"><label>Site <input name="site" tabindex="-1" autocomplete="off"></label></div>
        <button class="votos__opcao" type="submit">Enviar recado</button>
        <p class="recado__aviso" data-recado-aviso></p>
      </form>
      <p class="so-leitor" role="status" data-votos-status></p>
    </div>"""


def _objetivos_e_desafio(episodio: Mapping[str, Any], roteiro: Mapping[str, Any]) -> str:
    objetivos = "".join(f"<li>{escape(o)}</li>" for o in episodio.get("objetivos", []))
    return f"""<div class="episodio__detalhes">
      <div>
        <h4>Ao final, você deve conseguir</h4>
        <ul class="lista-marcada">{objetivos}</ul>
      </div>
      <div class="desafio">
        <h4>Desafio do episódio</h4>
        <p>{escape(roteiro.get('desafio', ''))}</p>
      </div>
    </div>"""


def _selo(item: Mapping[str, Any]) -> str:
    """Quantas afirmações a segunda IA revisou, e o link para o relatório: quem duvidar confere."""
    revisoes = item["revisoes"]
    if not revisoes:
        return ""
    afirmacoes = len(revisoes[-1].get("afirmacoes", []))
    relatorio = item["relatorio"]
    return (f'<p class="selo"><svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-check"/></svg>'
            f"{afirmacoes} afirmações revisadas por uma 2ª IA, aprovado na {len(revisoes)}ª revisão · "
            f'<a href="{escape(relatorio)}" rel="noopener">ver o relatório</a></p>')


def _dobra_transcricao(roteiro: Mapping[str, Any], personas: Mapping[str, Any]) -> str:
    falas = roteiro.get("falas", [])
    transcricao = "\n".join(
        f'<p><span class="fala__quem fala__quem--{escape(f["persona"])}">'
        f'{escape(personas.get(f["persona"], {}).get("nome", f["persona"]))}</span>{escape(f["texto"])}</p>'
        for f in falas
    )
    palavras = f'{sum(len(f["texto"].split()) for f in falas):,}'.replace(",", ".")
    return f"""<details class="dobra">
      <summary>Transcrição <span class="dobra__extra">{palavras} palavras</span></summary>
      <div class="transcricao" tabindex="0" role="region" aria-label="Transcrição do episódio">{transcricao}</div>
    </details>"""


def _fontes(roteiro: Mapping[str, Any]) -> str:
    return f'<ul class="fontes">{"".join(f"<li>{escape(f)}</li>" for f in roteiro.get("fontes", []))}</ul>'


def _links(item: Mapping[str, Any], link_permanente: str) -> str:
    return f"""<p class="episodio__links"><a href="{escape(item['publicacao']['url_audio'])}" download>Baixar o MP3</a>
      <span aria-hidden="true">·</span> <a href="{escape(link_permanente)}">Link deste episódio</a></p>"""


_ESTADO_DO_PROXIMO = {
    AGUARDANDO_PUBLICACAO: "Roteiro aprovado na revisão. Falta só gravar a voz e publicar.",
}
_ESTADO_PADRAO = "Fontes conferidas. O roteiro é o próximo a ser escrito."


_DIAS_POR_EXTENSO = {"segunda": "segunda", "terca": "terça", "quarta": "quarta", "quinta": "quinta",
                     "sexta": "sexta", "sabado": "sábado", "domingo": "domingo"}


def _nome_da_saga(sid: str) -> str:
    return next((nome for id_, nome, _ in SAGAS if id_ == sid), sid)


def _vez_da_saga(config: Mapping[str, Any], saga_id: str) -> str:
    """Por que o próximo é desta saga, lido de agenda.modo para o texto não mentir quando o modo mudar."""
    agenda = config["agenda"]
    vez = f"Agora é a vez da saga {_nome_da_saga(saga_id)}"
    if agenda["modo"] == "rotacao_semanal":
        return f"{vez}: cada dia da semana é de uma saga, e o episódio sai na saga do dia."
    if agenda["modo"] == "saga_unica":
        return f"{vez}: por enquanto, todos os episódios saem dela, na ordem do currículo."
    return f"{vez}: as sagas se revezam, e sai a que está há mais tempo sem episódio novo."


def _ordem_dos_episodios(config: Mapping[str, Any]) -> str:
    agenda = config["agenda"]
    if agenda["modo"] == "rotacao_semanal":
        rotacao = agenda["rotacao_semanal"]
        dias = ", ".join(f"{_DIAS_POR_EXTENSO[dia]} {_nome_da_saga(rotacao[dia])}"
                         for dia in DIAS_DA_SEMANA if dia in rotacao)
        regra = f"Cada dia da semana é de uma saga ({dias}), e dentro dela os episódios seguem o currículo."
    elif agenda["modo"] == "saga_unica":
        regra = (f"Por enquanto sai uma saga só, {_nome_da_saga(agenda['saga_unica'])}, "
                 "um episódio depois do outro, na ordem do currículo.")
    else:
        regra = ("As sagas se revezam: sai a que está há mais tempo sem episódio novo, "
                 "e dentro dela o próximo do currículo.")
    if config["episodio"].get("exigir_referencias_verificadas"):
        regra += " Só entra na vez o episódio com as referências já conferidas no livro; se não tiver, passa a vez."
    return regra


def _secao_proximo(proximo: Proximo | None, config: Mapping[str, Any]) -> str:
    if proximo is None:
        return _secao_proximo_vazio()
    objetivos = "".join(f"<li>{escape(o)}</li>" for o in proximo.episodio.dados.get("objetivos", []))
    aprendizado = f"""
      <h3 class="proximo__rotulo">Ao final, você deve conseguir</h3>
      <ul class="lista-marcada">{objetivos}</ul>""" if objetivos else ""
    estado = _ESTADO_DO_PROXIMO.get(proximo.estado, _ESTADO_PADRAO)
    return f"""<section class="secao secao--sem-topo" id="proximo">
  <div class="largura">
    <article class="proximo" data-saga="{escape(proximo.saga.id)}">
      {_etiqueta(proximo.saga, proximo.episodio.id)}
      <div class="proximo__capa" aria-hidden="true"><span class="proximo__codigo">{_codigo(proximo.episodio.id)}</span></div>
      <div class="proximo__corpo">
        <p class="sobretitulo">Próximo episódio</p>
        <h2 class="proximo__titulo">{escape(proximo.episodio.titulo)}</h2>
        <p class="proximo__vez">{escape(_vez_da_saga(config, proximo.saga.id))}</p>{aprendizado}
        <p class="proximo__estado">{escape(estado)}</p>
      </div>
    </article>
  </div>
</section>"""


def _secao_proximo_vazio() -> str:
    return """<section class="secao secao--sem-topo" id="proximo">
  <div class="largura">
    <article class="proximo proximo--vazio">
      <div class="proximo__capa" aria-hidden="true"><svg class="proximo__peba" viewBox="0 0 128 80"><use href="#peba"/></svg></div>
      <div class="proximo__corpo">
        <p class="sobretitulo">Próximo episódio</p>
        <h2 class="proximo__titulo">Ainda cavando o próximo</h2>
        <p class="proximo__texto">Episódio novo só sai depois que as referências dele são conferidas no livro.
          Assim que isso acontecer, ele aparece aqui e chega sozinho no seu app de podcast.</p>
        <p class="proximo__acao"><a class="botao botao--contorno" href="#assinar">Assinar o feed</a></p>
      </div>
    </article>
  </div>
</section>"""


def _secao_vozes(personas: Mapping[str, Any]) -> str:
    nomes_saga = {sid: nome for sid, nome, _ in SAGAS}
    cartoes = []
    ordem = sorted(personas.values(), key=lambda p: (p.get("papel") != "apresentador", p["nome"]))
    for persona in ordem:
        cor = ""
        if persona.get("papel") == "apresentador":
            papel = "Apresentador, em todas as sagas"
        else:
            sagas_da_voz = [s for s in persona.get("sagas", []) if s in nomes_saga]
            nomes = [nomes_saga[s] for s in sagas_da_voz]
            papel = f"Voz convidada da saga {', '.join(nomes)}" if nomes else "Voz convidada"
            # A voz convidada veste a cor da saga dela; o apresentador fica sem, porque está em todas.
            cor = f' data-saga="{escape(sagas_da_voz[0])}"' if sagas_da_voz else ""
        bordao = (persona.get("bordoes") or [""])[0]
        cartoes.append(f"""<article class="voz voz--{escape(persona['id'])}"{cor}>
  <div class="voz__inicial" aria-hidden="true">{escape(persona['nome'][0])}</div>
  <h3>{escape(persona['nome'])}</h3>
  <p class="voz__papel">{escape(papel)}</p>
  <p>{escape(' '.join(persona.get('historico', '').split()))}</p>
  {f'<blockquote class="voz__bordao">{escape(bordao)}</blockquote>' if bordao else ''}
</article>""")
    return f"""<section class="secao secao--alternada" id="vozes">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Quem conversa</p>
      <h2 class="secao__titulo">Uma pessoa pergunta, a outra já errou antes</h2>
      <p class="secao__lead">As vozes são personagens fictícios, com história fixa e voz sintética. Quem apresenta faz
        as perguntas que você faria; quem é convidado desmonta a resposta fácil e conta o que viu dar errado. As
        histórias são inventadas para ilustrar; os conceitos passam pela revisão.</p>
    </div>
    <div class="vozes">{''.join(cartoes)}</div>
  </div>
</section>"""


def _secao_sagas(sagas: Mapping[str, Any], publicados: Sequence[Mapping[str, Any]]) -> str:
    por_saga: dict[str, int] = {}
    for item in publicados:
        por_saga[item["saga"].id] = por_saga.get(item["saga"].id, 0) + 1
    cartoes = []
    for indice, (sid, nome, pergunta) in enumerate(SAGAS, start=1):
        saga = sagas.get(sid)
        feitos = por_saga.get(sid, 0)
        if saga and feitos:
            total = len(saga.episodios)
            estado = f'<span class="saga__estado saga__estado--ativa">No ar · {feitos} de {total}</span>'
            progresso = f'<span class="saga__progresso" style="--p:{feitos / total if total else 0:.3f}"></span>'
            classe = "saga saga--ativa"
            # Sem JS o filtro não roda e o link abre a lista completa, que continua servindo.
            titulo = (f'<a class="saga__link" href="{PAGINA_EPISODIOS}?saga={escape(sid)}">{escape(nome)}'
                      '<span class="so-leitor">: ver os episódios</span></a>')
            ver = '<span class="saga__ver" aria-hidden="true">Ver episódios →</span>'
        else:
            estado = '<span class="saga__estado">Em breve</span>'
            progresso = ""
            classe = "saga"
            titulo = escape(nome)
            ver = ""
        cartoes.append(f"""<li class="{classe}" data-saga="{escape(sid)}">
  <span class="saga__numero">{indice:02d}</span>
  <h3>{titulo}</h3>
  <p>{escape(pergunta)}</p>
  {estado}{progresso}{ver}
</li>""")
    return f"""<section class="secao" id="sagas">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">O caminho inteiro</p>
      <h2 class="secao__titulo">Sete sagas, uma pergunta cada</h2>
      <p class="secao__lead">Do código à estratégia da empresa. Cada saga tem seu currículo, suas referências
        e sua convidada, e um tema pertence à saga cuja pergunta ele responde.</p>
    </div>
    <ol class="sagas">{''.join(cartoes)}</ol>
  </div>
</section>"""


def _primeiro_nome(config: Mapping[str, Any]) -> str:
    return _config_do_site(config)["criador"]["nome"].split()[0]


def _secao_como(config: Mapping[str, Any]) -> str:
    """As etapas com quem faz cada uma (pessoa, IA ou código), nas mesmas cores de docs/fluxo-do-episodio.md."""
    revisoes = max_revisoes(config["revisao"]["max_ciclos"])
    pessoa = _primeiro_nome(config)
    quem = {"pessoa": pessoa, "ia": "IA", "codigo": "Código"}
    passos = [
        ("pessoa", "Currículo", f"{pessoa} escolhe a obra e o capítulo de cada episódio e confere que a fonte "
                                "existe e trata do tema. Objetivos e pré-requisitos também são escritos à mão."),
        ("codigo", "A vez de cada saga", _ordem_dos_episodios(config)),
        ("ia", "Caso", "Busca uma notícia recente que ilustre o tema. Se nenhuma servir, usa um cenário hipotético "
                       "e avisa."),
        ("ia", "Roteiro", "Uma IA escreve o diálogo seguindo a história e o jeito de falar de cada personagem."),
        ("ia", "Revisão", f"Outra IA, sem ver como o roteiro foi feito, revisa cada afirmação com o que sabe e, na "
                          f"dúvida, com uma busca. São até {revisoes} revisões; se não aprovar, o episódio não sai."),
        ("codigo", "Voz e feed", "O áudio é sintetizado, montado com a vinheta e publicado no feed, com as fontes "
                                 "nas notas."),
        ("pessoa", "Escuta", f"Depois de publicado, {pessoa} ouve o episódio, registra o que achou e manda "
                             "regravar se o áudio saiu ruim."),
    ]
    itens = "\n".join(
        f'<li><span class="passo__num">{i}</span><span class="passo__quem passo__quem--{papel}">{escape(quem[papel])}</span>'
        f"<h3>{escape(t)}</h3><p>{escape(d)}</p></li>"
        for i, (papel, t, d) in enumerate(passos, start=1)
    )
    return f"""<section class="secao secao--escura" id="como">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Como cada episódio nasce</p>
      <h2 class="secao__titulo">Feito por IA, com gente nas duas pontas</h2>
      <p class="secao__lead">Ninguém grava: as vozes são sintéticas. Mas {escape(pessoa)} escolhe as fontes antes e
        ouve o episódio depois, e cada etapa fica registrada no repositório, com uma regra simples: roteiro que a
        revisão reprova não vira episódio.</p>
    </div>
    <ol class="passos">{itens}</ol>
  </div>
</section>"""


def _secao_assinar(url_feed: str, meta: Mapping[str, Any]) -> str:
    return f"""<section class="secao" id="assinar">
  <div class="largura assinar">
    <div>
      <p class="sobretitulo">Ouça no seu app</p>
      <h2 class="secao__titulo">Assine pelo feed</h2>
      <p class="secao__lead">Cole o endereço em qualquer app de podcast que aceite RSS, como AntennaPod, Pocket Casts,
        Apple Podcasts ou Overcast. Episódio novo chega sozinho.</p>
    </div>
    <div class="feed">
      <label class="feed__rotulo" for="url-feed">Endereço do feed</label>
      <div class="feed__linha">
        <input id="url-feed" class="feed__url" type="text" readonly value="{escape(url_feed)}">
        <button class="botao feed__copiar" type="button" data-copiar="url-feed">Copiar</button>
      </div>
      <p class="feed__extra"><a href="{escape(url_feed)}">Abrir o XML</a>
        <span aria-hidden="true">·</span> <a href="{escape(meta['url_repositorio'])}">Código e roteiros no GitHub</a></p>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- sobre


def _sobre_definicao(meta: Mapping[str, Any], criador: str) -> str:
    """O primeiro parágrafo responde sozinho o que é o podcast: é o trecho que uma IA tende a citar."""
    nomes = [nome for _, nome, _ in SAGAS]
    sagas = ", ".join(nomes[:-1]) + " e " + nomes[-1]
    return f"""<section class="secao sobre" id="sobre">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Sobre</p>
      <h1 class="secao__titulo">O que é o {escape(meta['titulo'])}</h1>
    </div>
    <p class="sobre__definicao">O {escape(meta['titulo'])} é um podcast diário em português sobre arquitetura
      de software, criado por {escape(criador)}. São sete sagas ({escape(sagas)}), com episódios de 15 a
      20 minutos em forma de diálogo e um desafio prático no fim de cada um. O conteúdo é gerado por
      inteligência artificial: {escape(criador)} escolhe as fontes de cada episódio, uma segunda IA revisa as
      afirmações do roteiro antes do áudio, e ele ouve cada episódio depois de publicado.</p>
  </div>
</section>"""


def _sobre_proposta() -> str:
    sagas = "".join(
        f'<li data-saga="{escape(sid)}"><strong>{escape(nome)}</strong> {escape(pergunta)}</li>'
        for sid, nome, pergunta in SAGAS
    )
    return f"""<section class="secao secao--sem-topo" id="proposta">
  <div class="largura sobre__bloco">
    <h2 class="secao__titulo secao__titulo--menor">Pra quem é</h2>
    <div class="sobre__texto">
      <p>Pra quem programa e quer entender por que os sistemas são desenhados do jeito que são: de quem está
        começando na área a quem já escreve código todo dia e quer dar o passo para a arquitetura.</p>
      <p>Cada saga tem um currículo próprio, com os episódios em ordem, e responde a uma pergunta:</p>
      <ul class="sobre__sagas">{sagas}</ul>
    </div>
  </div>
</section>"""


def _sobre_como(meta: Mapping[str, Any], pessoa: str) -> str:
    return f"""<section class="secao secao--alternada" id="como-e-feito">
  <div class="largura sobre__bloco">
    <h2 class="secao__titulo secao__titulo--menor">Como é feito</h2>
    <div class="sobre__texto">
      <p>Antes de tudo, {escape(pessoa)} escolhe a obra e o capítulo de cada episódio e confere que a fonte existe e
        trata do tema. Uma IA escreve o roteiro a partir desse currículo. Outra IA, sem ver como o roteiro foi
        feito, revisa cada afirmação com o que sabe e, na dúvida, com uma busca; se o roteiro não for
        aprovado, o episódio não sai. Depois, as vozes são sintetizadas e o episódio vai para o feed.</p>
      <p>Por último, ele ouve cada episódio depois de publicado, registra o que achou e manda regravar quando o
        áudio sai ruim. A revisão tem um limite que vale dizer: a revisora é do mesmo modelo que a roteirista e
        pode ter os mesmos pontos cegos. Por isso cada relatório de revisão fica aberto, ao lado do roteiro.</p>
      <p>Tudo fica registrado e aberto no repositório: currículo, roteiros, revisões e código.</p>
      <p class="sobre__acoes"><a class="botao botao--contorno" href="../#como">Ver as etapas</a>
        <a class="botao botao--contorno" href="{escape(meta['url_repositorio'])}">Código e roteiros no GitHub</a></p>
    </div>
  </div>
</section>"""


def _sobre_quem_faz(criador: Mapping[str, Any]) -> str:
    # Cada pedaço entre "·" não quebra por dentro: a linha quebra entre eles ("Natal, RN" fica junto).
    partes = [p.strip() for campo in (criador["papel"], criador["cidade"]) for p in campo.split("·") if p.strip()]
    linha = " · ".join(f'<span class="criador__parte">{escape(parte)}</span>' for parte in partes)
    papel = f'<p class="criador__papel">{linha}</p>' if linha else ""
    bio = f'<p class="criador__bio">{escape(criador["bio"])}</p>' if criador["bio"] else ""
    links = "".join(
        f'<a class="botao botao--contorno botao--pequeno" href="{escape(link["url"])}" rel="me noopener">'
        f'{escape(_rotulo_do_link(link))}<svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-fora"/></svg></a>'
        for link in criador["links"]
    )
    links_html = f'<p class="criador__links">{links}</p>' if links else ""
    retrato = (f'<img class="criador__foto" src="../{escape(criador["foto"])}" alt="Foto de {escape(criador["nome"])}"'
               ' width="104" height="104" loading="lazy" decoding="async">'
               if criador["foto"] else
               f'<div class="criador__inicial" aria-hidden="true">{escape(criador["nome"][:1])}</div>')
    return f"""<section class="secao" id="quem-faz">
  <div class="largura sobre__bloco">
    <h2 class="secao__titulo secao__titulo--menor">Quem faz</h2>
    <article class="criador">
      {retrato}
      <div>
        <h3 class="criador__nome">{escape(criador["nome"])}</h3>
        {papel}
        {bio}
        {links_html}
      </div>
    </article>
  </div>
</section>"""


def _rotulo_do_link(link: Mapping[str, str]) -> str:
    """"GitHub · lucas-jdev": o nome do serviço e o usuário, que é o último pedaço da URL."""
    usuario = link["url"].rsplit("/", 1)[-1]
    rotulo = link["rotulo"] or link["url"].split("/")[2]
    return f"{rotulo} · {usuario}" if usuario and "." not in usuario else rotulo


def _sobre_nome(meta: Mapping[str, Any]) -> str:
    return f"""<section class="secao secao--sem-topo" id="nome">
  <div class="largura sobre__bloco">
    <h2 class="secao__titulo secao__titulo--menor">Por que {escape(meta['titulo'])}</h2>
    <div class="sobre__texto sobre__nome">
      <svg class="sobre__peba" viewBox="0 0 128 80" aria-hidden="true"><use href="#peba"/></svg>
      <p>O nome vem do tatu-peba, bicho do Nordeste, de onde o {escape(meta['titulo'])} é feito, que cava a terra
        até achar o que procura. Daí o lema: cava até achar o porquê. Não tem relação com PEBCAK, a gíria de
        suporte técnico.</p>
    </div>
  </div>
</section>"""


def _rodape(meta: Mapping[str, Any], config: Mapping[str, Any], raiz: str = "") -> str:
    credito = (config.get("audio", {}).get("vinheta") or {}).get("credito", "")
    credito_html = f"<p>{escape(credito)}</p>" if credito else ""
    return f"""<footer class="rodape">
  <div class="faixa faixa--fina" role="presentation"></div>
  <div class="largura rodape__grade">
    <div class="rodape__marca">
      <svg viewBox="0 0 128 80" aria-hidden="true"><use href="#peba"/></svg>
      <p><strong>{escape(meta['titulo'])}</strong><br>Cava até achar o porquê.</p>
    </div>
    <div class="rodape__texto">
      <p>Conteúdo gerado por inteligência artificial, com fontes escolhidas à mão e afirmações revisadas por
        uma segunda IA.
        Episódios e roteiros sob {escape(meta['licenca'])}; código sob MIT.</p>
      {credito_html}
      <p><a href="{escape(meta['url_repositorio'])}">Repositório</a> · <a href="{raiz}feed.xml">RSS</a>
        · <a href="{raiz}{PAGINA_SOBRE}">{escape(_config_do_site(config)["criador"]["nome"])}</a></p>
    </div>
  </div>
</footer>"""


# ---------------------------------------------------------------- SVG e esqueleto


# O tatu-peba em traço de xilogravura: massa de tinta com os cortes das cintas.
_SIMBOLOS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="peba" viewBox="0 0 128 80">
    <path fill="currentColor" d="M104 55c9 1 16 6 22 15-8-3-15-6-23-7z"/>
    <path fill="currentColor" d="M36 59h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm14 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm34 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zm14 0h8v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2z"/>
    <path fill="currentColor" d="M28 60c0-27 19-44 42-44s40 17 40 44z"/>
    <path fill="currentColor" d="M36 44c-9-2-18 2-25 8L3 59c-1 1-1 4 2 4h30z"/>
    <path fill="currentColor" d="M33 47c-3-6-2-13 2-15 3 3 3 10 0 15z"/>
    <g fill="none" stroke="var(--corte, #f4ecdd)" stroke-linecap="round">
      <path stroke-width="2.4" d="M50 23c-3 11-4 24-4 34M61 18c-2 12-2 26-2 39M72 17c0 13 0 27 0 40M83 19c2 12 2 25 2 38M94 25c3 10 4 21 4 32"/>
      <path stroke-width="1.6" d="M32 56c24-3 50-3 76 0"/>
      <path stroke-width="1.4" d="M38 30l4 3m-6 4 4 2m62-9-4 3m6 4-4 2"/>
    </g>
    <circle cx="16" cy="54" r="1.8" fill="var(--corte, #f4ecdd)"/>
  </symbol>
  <symbol id="i-play" viewBox="0 0 24 24"><path fill="currentColor" d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z"/></symbol>
  <symbol id="i-pause" viewBox="0 0 24 24"><path fill="currentColor" d="M6 4h4v16H6zm8 0h4v16h-4z"/></symbol>
  <symbol id="i-curti" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" d="M3 10h4v10H3zm4 0 4-7c1.6 0 2.6 1.3 2.2 2.8L12.6 9H19a2 2 0 0 1 2 2.3l-1.2 6.9A2 2 0 0 1 17.8 20H7"/></symbol>
  <symbol id="i-nao_curti" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" transform="rotate(180 12 12)" d="M3 10h4v10H3zm4 0 4-7c1.6 0 2.6 1.3 2.2 2.8L12.6 9H19a2 2 0 0 1 2 2.3l-1.2 6.9A2 2 0 0 1 17.8 20H7"/></symbol>
  <symbol id="i-fora" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M14 4h6v6m0-6-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="m5 12.5 4.5 4.5L19 7.5"/></symbol>
</svg>"""


# A toca: do chão até o porquê, atravessando as camadas de terra.
_ILUSTRACAO_TOCA = """<figure class="toca" aria-label="Ilustração: um tatu-peba cava um túnel que atravessa três camadas de terra, chamadas o quê, como e por quê.">
  <svg viewBox="0 0 440 420" role="img" aria-hidden="true">
    <rect class="toca__camada1" x="0" y="120" width="440" height="100"/>
    <rect class="toca__camada2" x="0" y="220" width="440" height="100"/>
    <rect class="toca__camada3" x="0" y="320" width="440" height="100"/>
    <g class="toca__pedras">
      <circle cx="58" cy="168" r="5"/><circle cx="392" cy="196" r="4"/><circle cx="150" cy="270" r="6"/>
      <circle cx="402" cy="282" r="5"/><circle cx="40" cy="372" r="6"/><circle cx="118" cy="402" r="4"/>
      <ellipse cx="250" cy="190" rx="9" ry="5"/><ellipse cx="320" cy="350" rx="10" ry="5"/>
    </g>
    <path class="toca__tunel" d="M300 120c0 40-70 40-80 85s70 55 50 105-120 25-120 70"/>
    <path class="toca__tunel-borda" d="M300 120c0 40-70 40-80 85s70 55 50 105-120 25-120 70"/>
    <path class="toca__chao" d="M0 120h440"/>
    <g class="toca__mato">
      <path d="M40 120c2-10 6-16 12-20m-6 20c0-8-4-14-10-18m60 18c1-12 6-18 12-22m-6 22c-1-8-5-12-11-15"/>
      <path d="M352 120c2-12 7-19 14-23m-8 23c-1-9-6-15-12-18m50 18c1-8 4-13 9-16"/>
    </g>
    <ellipse class="toca__boca" cx="300" cy="121" rx="22" ry="5"/>
    <g class="toca__rotulos">
      <text x="424" y="176" text-anchor="end">o quê</text>
      <text x="424" y="276" text-anchor="end">como</text>
      <text x="424" y="376" text-anchor="end" class="toca__rotulo-fundo">por quê</text>
    </g>
    <svg x="40" y="334" width="140" height="88" viewBox="0 0 128 80" class="toca__peba"><use href="#peba"/></svg>
    <g class="toca__brilho"><circle cx="40" cy="392" r="3"/><circle cx="30" cy="378" r="2"/><circle cx="46" cy="374" r="2"/></g>
  </svg>
</figure>"""


_PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>document.documentElement.classList.add("js")</script>
<title>{titulo}</title>
<meta name="description" content="{descricao}">
<meta name="author" content="{autor}">
<meta name="robots" content="index, follow, max-image-preview:large">
{verificacao}<meta name="theme-color" content="#f4ecdd" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#16130f" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="website">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{descricao}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="pt_BR">
<meta property="og:site_name" content="{nome}">
<meta property="og:image" content="{imagem}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="{imagem_largura}">
<meta property="og:image:height" content="{imagem_altura}">
<meta property="og:image:alt" content="{imagem_descricao}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{titulo}">
<meta name="twitter:description" content="{descricao}">
<meta name="twitter:image" content="{imagem}">
<meta name="twitter:image:alt" content="{imagem_descricao}">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="{nome}" href="{url_feed}">
<link rel="icon" href="{raiz}favicon.ico" sizes="48x48">
<link rel="icon" href="{raiz}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{raiz}apple-touch-icon.png">
<link rel="preload" href="{raiz}fontes/literata-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{raiz}fontes/literata-latin-700-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{raiz}fontes/alfa-slab-one-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{raiz}amarracao-verso.svg" as="image" fetchpriority="high">
<link rel="preload" href="{raiz}amarracao-frente.svg" as="image" fetchpriority="high">
<link rel="stylesheet" href="{raiz}estilo.css">
<script defer src="{raiz}app.js"></script>
<script type="application/ld+json">{dados_estruturados}</script>
{analytics}
</head>
<body>
{simbolos}
<a class="pular" href="#{pular_para}">{pular_texto}</a>
{cabecalho}
<main>
{conteudo}
</main>
{rodape}
</body>
</html>
"""
