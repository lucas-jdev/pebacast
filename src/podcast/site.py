"""Página inicial do Pebacast no GitHub Pages.

Gera o index.html a partir do que já está no repositório (currículo, personas e
episódios publicados) e copia os arquivos estáticos de site/. O feed continua
saindo de podcast.publicacao: esta página é só a vitrine.

    python -m podcast.publicacao feed --site _site
"""

import json
import shutil
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from podcast.roteiro import FUSO_BRASILIA, Projeto
from podcast.validacao import NOTICIA, PASTA_REVISOES, PUBLICACAO, ROTEIRO

ARQUIVOS_ESTATICOS = "site"

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# As sete sagas e suas perguntas centrais (docs/fronteiras-das-sagas.md).
SAGAS = (
    ("software", "Software", "Como um sistema é organizado por dentro e por quê?"),
    ("solucoes", "Soluções", "Quais peças resolvem este problema de negócio e como elas se conectam?"),
    ("sistemas", "Sistemas", "Como as partes se comportam juntas, principalmente quando algo falha?"),
    ("dados", "Dados e Informação", "Como a informação é modelada, governada e flui pela organização?"),
    ("infraestrutura", "Infraestrutura", "Onde e como tudo isso roda, com qual custo e confiabilidade?"),
    ("seguranca", "Segurança", "Quem pode fazer o quê, e o que acontece quando alguém tenta o que não deveria?"),
    ("corporativa", "Corporativa", "Como a tecnologia sustenta a estratégia da organização?"),
)


def escrever_pagina(projeto: Projeto, site: Path, arquivo_feed: str) -> None:
    estaticos = projeto.raiz / ARQUIVOS_ESTATICOS
    if estaticos.is_dir():
        shutil.copytree(estaticos, site, dirs_exist_ok=True)
    (site / "index.html").write_text(gerar_index(projeto, arquivo_feed), encoding="utf-8")


def gerar_index(projeto: Projeto, arquivo_feed: str) -> str:
    config = projeto.config()
    meta = config["feed"]
    sagas = projeto.sagas()
    personas = projeto.personas()
    publicados = _publicados(projeto)
    url_feed = meta["url_site"].rstrip("/") + "/" + arquivo_feed

    ultimo, anteriores = (publicados[0], publicados[1:]) if publicados else (None, [])
    proximos = [
        (saga, episodio)
        for saga in _sagas_na_ordem_de_estudo(sagas, publicados)
        for episodio in saga.episodios
        if not (projeto.episodios / episodio.id / PUBLICACAO).exists()
    ]

    secoes = [
        _hero(ultimo),
        _faixa(),
        _secao_ultimo(ultimo, personas),
        _secao_anteriores(anteriores, personas),
        _secao_proximos(proximos),
        _secao_vozes(personas, sagas),
        _secao_sagas(sagas, publicados),
        _secao_como(config),
        _secao_assinar(url_feed, meta),
    ]
    descricao = " ".join(meta["descricao"].split())
    return _PAGINA.format(
        titulo=escape(meta["titulo"]),
        descricao=escape(descricao),
        url_site=escape(meta["url_site"]),
        url_feed=escape(url_feed),
        simbolos=_SIMBOLOS,
        cabecalho=_cabecalho(meta),
        conteudo="\n".join(s for s in secoes if s),
        rodape=_rodape(meta, config),
    )


# ---------------------------------------------------------------- dados


def _publicados(projeto: Projeto) -> list[dict[str, Any]]:
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
            })
    itens.sort(key=lambda item: item["publicacao"]["publicado_em"], reverse=True)
    return itens


def _sagas_na_ordem_de_estudo(sagas: Mapping[str, Any], publicados: Sequence[Mapping[str, Any]]) -> list[Any]:
    em_andamento = {item["saga"].id for item in publicados}
    posicao = {sid: indice for indice, (sid, _, _) in enumerate(SAGAS)}
    return sorted(sagas.values(), key=lambda saga: (saga.id not in em_andamento, posicao.get(saga.id, len(SAGAS))))


def _ler_json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _data_por_extenso(iso: str) -> str:
    data = datetime.fromisoformat(iso).astimezone(FUSO_BRASILIA)
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


def _data_curta(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(FUSO_BRASILIA).date().isoformat()


def _duracao(segundos: int) -> str:
    return f"{segundos // 60}:{segundos % 60:02d}"


def _minutos(segundos: int) -> str:
    return f"{round(segundos / 60)} min"


def _numero(episodio_id: str) -> str:
    return episodio_id.rsplit("-", 1)[-1]


# ---------------------------------------------------------------- seções


def _cabecalho(meta: Mapping[str, Any]) -> str:
    return f"""<header class="topo">
  <div class="largura topo__linha">
    <a class="marca" href="#inicio" aria-label="{escape(meta['titulo'])}, início">
      <svg class="marca__peba" viewBox="0 0 128 80" aria-hidden="true"><use href="#peba"/></svg>
      <span class="marca__nome">{escape(meta['titulo'])}</span>
    </a>
    <nav class="topo__nav" aria-label="Seções">
      <a href="#episodios">Episódios</a>
      <a href="#sagas">Sagas</a>
      <a href="#como">Como funciona</a>
      <a class="botao botao--pequeno" href="#assinar">Assinar</a>
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
        Cada episódio parte de um caso real, pesa os trade-offs sem torcida e termina com um desafio
        pra você levar pro trabalho.</p>
      <div class="hero__acoes">
        {acao}
        <a class="botao botao--contorno" href="#assinar">Assinar o feed</a>
      </div>
      <p class="pronuncia"><span class="pronuncia__fala">PÉ-ba-cast</span>
        com E aberto, de tatu-peba: o bicho da caatinga que não para de cavar.</p>
    </div>
    {_ILUSTRACAO_TOCA}
  </div>
</section>"""


def _faixa() -> str:
    return '<div class="faixa" role="presentation"></div>'


def _secao_ultimo(item: Mapping[str, Any] | None, personas: Mapping[str, Any]) -> str:
    if item is None:
        return """<section class="secao" id="episodios">
  <div class="largura"><h2 class="secao__titulo">Episódios</h2>
  <p class="vazio">O primeiro episódio está sendo cavado. Assine o feed pra receber assim que sair.</p></div>
</section>"""
    return f"""<section class="secao" id="episodios">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Episódio mais recente</p>
      <h2 class="secao__titulo">Pra ouvir agora</h2>
    </div>
    {_episodio(item, personas, destaque=True)}
  </div>
</section>"""


def _secao_anteriores(itens: Sequence[Mapping[str, Any]], personas: Mapping[str, Any]) -> str:
    if not itens:
        return ""
    lista = "\n".join(_episodio(item, personas, destaque=False) for item in itens)
    return f"""<section class="secao secao--sem-topo" id="anteriores">
  <div class="largura">
    <h2 class="secao__titulo secao__titulo--menor">Episódios anteriores</h2>
    <div class="lista-episodios">{lista}</div>
  </div>
</section>"""


def _episodio(item: Mapping[str, Any], personas: Mapping[str, Any], destaque: bool) -> str:
    episodio, publicacao, roteiro = item["episodio"], item["publicacao"], item["roteiro"]
    noticia, revisoes, saga = item["noticia"], item["revisoes"], item["saga"]
    eid = escape(episodio["id"])
    objetivos = "".join(f"<li>{escape(o)}</li>" for o in episodio.get("objetivos", []))
    fontes = "".join(f"<li>{escape(f)}</li>" for f in roteiro.get("fontes", []))

    if noticia.get("tipo") == "noticia":
        caso = (f'<p class="caso"><span class="caso__rotulo">Ponto de partida</span>'
                f'<a href="{escape(noticia["url"])}" rel="noopener">{escape(noticia["titulo"])}</a>'
                f' <span class="caso__fonte">{escape(noticia["fonte"])}</span></p>')
    else:
        caso = '<p class="caso"><span class="caso__rotulo">Ponto de partida</span>Um cenário hipotético.</p>'

    selo = ""
    if revisoes:
        afirmacoes = len(revisoes[-1].get("afirmacoes", []))
        ciclos = len(revisoes)
        selo = (f'<p class="selo"><svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-check"/></svg>'
                f"{afirmacoes} afirmações checadas contra as fontes, aprovado na {ciclos}ª revisão</p>")

    transcricao = "\n".join(
        f'<p><span class="fala__quem fala__quem--{escape(f["persona"])}">'
        f'{escape(personas.get(f["persona"], {}).get("nome", f["persona"]))}</span>{escape(f["texto"])}</p>'
        for f in roteiro.get("falas", [])
    )
    palavras = f'{sum(len(f["texto"].split()) for f in roteiro.get("falas", [])):,}'.replace(",", ".")

    classe = "episodio episodio--destaque" if destaque else "episodio"
    return f"""<article class="{classe}" id="{eid}">
  <div class="episodio__capa" aria-hidden="true">
    <span class="episodio__saga">{escape(saga.nome)}</span>
    <span class="episodio__numero">{escape(_numero(episodio['id']))}</span>
    <svg class="episodio__peba" viewBox="0 0 128 80"><use href="#peba"/></svg>
  </div>
  <div class="episodio__corpo">
    <p class="episodio__meta">
      <time datetime="{escape(publicacao['publicado_em'])}">{escape(_data_por_extenso(publicacao['publicado_em']))}</time>
      <span aria-hidden="true">·</span> {escape(_minutos(publicacao['duracao_segundos']))}
      <span aria-hidden="true">·</span> {escape(saga.nome)}, episódio {escape(_numero(episodio['id']))}
    </p>
    <h3 class="episodio__titulo">{escape(episodio['titulo'])}</h3>
    {caso}
    <div class="player" data-duracao="{publicacao['duracao_segundos']}">
      <audio controls preload="none" src="{escape(publicacao['url_audio'])}"></audio>
      <button class="player__play" type="button" aria-label="Tocar">
        <svg class="player__icone-play" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-play"/></svg>
        <svg class="player__icone-pausa" aria-hidden="true" viewBox="0 0 24 24"><use href="#i-pause"/></svg>
      </button>
      <div class="player__trilha">
        <input class="player__barra" type="range" min="0" max="{publicacao['duracao_segundos']}" value="0" step="1" aria-label="Posição no episódio">
        <div class="player__tempos"><span class="player__atual">0:00</span><span>{escape(_duracao(publicacao['duracao_segundos']))}</span></div>
      </div>
      <button class="player__velocidade" type="button"><span class="so-leitor">Velocidade de reprodução: </span><span class="player__velocidade-valor">1×</span></button>
    </div>
    <div class="episodio__detalhes">
      <div>
        <h4>Ao final, você deve conseguir</h4>
        <ul class="lista-marcada">{objetivos}</ul>
      </div>
      <div class="desafio">
        <h4>Desafio do episódio</h4>
        <p>{escape(roteiro.get('desafio', ''))}</p>
      </div>
    </div>
    {selo}
    <details class="dobra">
      <summary>Transcrição <span class="dobra__extra">{palavras} palavras</span></summary>
      <div class="transcricao" tabindex="0" role="region" aria-label="Transcrição do episódio">{transcricao}</div>
    </details>
    <details class="dobra">
      <summary>Fontes</summary>
      <ul class="fontes">{fontes}</ul>
    </details>
    <p class="episodio__links"><a href="{escape(publicacao['url_audio'])}" download>Baixar o MP3</a>
      <span aria-hidden="true">·</span> <a href="#{eid}">Link deste episódio</a></p>
  </div>
</article>"""


def _secao_proximos(proximos: Sequence[tuple[Any, Any]]) -> str:
    if not proximos:
        return ""
    itens = "\n".join(
        f'<li><span class="proximo__num">{escape(_numero(ep.id))}</span>'
        f'<span class="proximo__titulo">{escape(ep.titulo)}</span>'
        f'<span class="proximo__saga">{escape(saga.nome)}</span></li>'
        for saga, ep in proximos[:6]
    )
    return f"""<section class="secao secao--sem-topo">
  <div class="largura">
    <h2 class="secao__titulo secao__titulo--menor">Na sequência</h2>
    <ol class="proximos">{itens}</ol>
  </div>
</section>"""


def _secao_vozes(personas: Mapping[str, Any], sagas: Mapping[str, Any]) -> str:
    nomes_saga = {saga.id: saga.nome for saga in sagas.values()}
    cartoes = []
    ordem = sorted(personas.values(), key=lambda p: (p.get("papel") != "apresentador", p["nome"]))
    for persona in ordem:
        if persona.get("papel") == "apresentador":
            papel = "Apresentador, em todas as sagas"
        else:
            nomes = [nomes_saga.get(s, s) for s in persona.get("sagas", [])]
            papel = f"Convidada da saga {', '.join(nomes)}" if nomes else "Convidada"
        bordao = (persona.get("bordoes") or [""])[0]
        cartoes.append(f"""<article class="voz voz--{escape(persona['id'])}">
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
      <p class="secao__lead">As vozes são personagens com história fixa. Quem apresenta faz as perguntas que você faria;
        quem é convidada desmonta a resposta fácil e conta o que viu dar errado.</p>
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
        else:
            estado = '<span class="saga__estado">Em breve</span>'
            progresso = ""
            classe = "saga"
        cartoes.append(f"""<li class="{classe}" style="--motivo:{indice}">
  <span class="saga__numero">{indice:02d}</span>
  <h3>{escape(nome)}</h3>
  <p>{escape(pergunta)}</p>
  {estado}{progresso}
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


def _secao_como(config: Mapping[str, Any]) -> str:
    ciclos = config["revisao"]["max_ciclos"]
    passos = [
        ("Currículo", "Cada episódio tem objetivos, pré-requisitos e referências escolhidos à mão, livro e capítulo."),
        ("Caso real", "Busca uma notícia recente que ilustre o tema. Se nenhuma servir, usa um cenário hipotético e avisa."),
        ("Roteiro", "Uma IA escreve o diálogo seguindo a história e o jeito de falar de cada personagem."),
        ("Revisão", f"Outra IA, sem ver como o roteiro foi feito, confere cada afirmação contra as fontes. "
                    f"Se não aprovar em {ciclos} rodadas, o episódio não sai."),
        ("Voz e feed", "O áudio é sintetizado, montado com a vinheta e publicado no feed, com as fontes nas notas."),
    ]
    itens = "\n".join(
        f'<li><span class="passo__num">{i}</span><h3>{escape(t)}</h3><p>{escape(d)}</p></li>'
        for i, (t, d) in enumerate(passos, start=1)
    )
    return f"""<section class="secao secao--escura" id="como">
  <div class="largura">
    <div class="secao__cabeca">
      <p class="sobretitulo">Como cada episódio nasce</p>
      <h2 class="secao__titulo">Feito por IA, conferido contra a fonte</h2>
      <p class="secao__lead">Não tem gente gravando. Tem um processo aberto, com cada etapa registrada no repositório,
        e uma regra simples: afirmação que não bate com a fonte derruba o episódio.</p>
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


def _rodape(meta: Mapping[str, Any], config: Mapping[str, Any]) -> str:
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
      <p>Conteúdo gerado por inteligência artificial e revisado contra as fontes citadas.
        Episódios e roteiros sob {escape(meta['licenca'])}; código sob MIT.</p>
      {credito_html}
      <p><a href="{escape(meta['url_repositorio'])}">Repositório</a> · <a href="feed.xml">RSS</a> · {escape(meta['autor'])}</p>
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
<title>{titulo} · arquitetura, um porquê por dia</title>
<meta name="description" content="{descricao}">
<meta name="theme-color" content="#f4ecdd" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#16130f" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="website">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{descricao}">
<meta property="og:url" content="{url_site}">
<meta property="og:locale" content="pt_BR">
<link rel="canonical" href="{url_site}">
<link rel="alternate" type="application/rss+xml" title="{titulo}" href="{url_feed}">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,400..800,50&family=Instrument+Sans:wght@400..700&display=swap">
<link rel="stylesheet" href="estilo.css">
<script defer src="app.js"></script>
</head>
<body>
{simbolos}
<a class="pular" href="#episodios">Pular para os episódios</a>
{cabecalho}
<main>
{conteudo}
</main>
{rodape}
</body>
</html>
"""
