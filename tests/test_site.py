import json
import re
from datetime import date
from pathlib import Path

import yaml

from podcast.site import (
    escrever_pagina,
    gerar_index,
    gerar_pagina_do_episodio,
    gerar_pagina_episodios,
    gerar_pagina_sobre,
    gerar_sitemap,
)
from tests.test_publicacao import _publicar
from tests.test_roteiro import (  # noqa: F401 (fixture)
    CONFIG,
    SAGA,
    _escrever_episodio,
    _gravar,
    _revisao,
    _roteiro,
    _usar_fila,
    projeto,
)

SAGA_SEM_EPISODIO_PUBLICADO = {
    **SAGA,
    "id": "corporativa",
    "nome": "Arquitetura Corporativa",
    "episodios": [{**SAGA["episodios"][0], "id": "co-001", "titulo": "Elevador do arquiteto"}],
}


def _ja_publicado(projeto, episodio, publicado_em, reescrever=True):
    if reescrever:
        _escrever_episodio(projeto, episodio)
    _gravar(projeto.episodios / episodio / "publicacao.json", {
        "guid": f"pebacast-{episodio}", "url_audio": f"https://cdn/{episodio}.mp3", "tamanho_bytes": 1,
        "duracao_segundos": 960, "publicado_em": publicado_em,
    })


def test_pagina_mostra_episodio_publicado_com_player_e_desafio(projeto, tmp_path):
    noticia = {"tipo": "noticia", "titulo": "Apagão <ao vivo>", "url": "https://n/1", "fonte": "Jornal",
               "data": "2026-11-01", "nota_relevancia": 8, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _publicar(projeto, tmp_path)

    pagina = gerar_index(projeto, "feed.xml")

    assert 'id="sw-001"' in pagina
    assert "Liste dois trade-offs." in pagina
    assert re.search(r'<audio controls preload="none"><source src="[^"]+" type="audio/mpeg"></audio>', pagina)
    assert "Apagão &lt;ao vivo&gt;" in pagina
    assert "feed.xml" in pagina


def test_pagina_sem_episodios_convida_a_assinar(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    assert "<audio" not in pagina
    assert "O primeiro episódio está sendo cavado." in pagina


def test_saga_so_fica_no_ar_quando_tem_episodio_publicado(projeto, tmp_path):
    _gravar(projeto.raiz / "curriculum" / "sagas" / "corporativa.yaml", SAGA_SEM_EPISODIO_PUBLICADO)
    _escrever_episodio(projeto, "sw-001")
    _publicar(projeto, tmp_path)

    pagina = gerar_index(projeto, "feed.xml")

    assert pagina.count("saga__estado--ativa") == 1
    assert "No ar · 1 de 3" in pagina
    assert "Dois" in pagina
    assert "Elevador do arquiteto" not in pagina


def test_inicial_mostra_so_o_ultimo_e_aponta_para_o_arquivo(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert 'id="sw-002"' in pagina
    assert 'id="sw-001"' not in pagina
    assert 'href="episodios.html">Ver os 2 episódios publicados' in pagina
    assert 'href="episodios/sw-002/">Link deste episódio' in pagina


def test_proximo_segue_a_fila_da_pipeline(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert pagina.count('class="proximo__titulo"') == 1
    assert 'class="proximo__titulo">sl-001<' in pagina
    assert "O roteiro é o próximo a ser escrito." in pagina


def test_roteiro_aprovado_e_o_proximo_mesmo_fora_da_ordem(projeto):
    _escrever_episodio(projeto, "sw-001")

    pagina = gerar_index(projeto, "feed.xml")

    assert 'class="proximo__titulo">Um<' in pagina
    assert "Roteiro aprovado na revisão." in pagina


def test_sem_episodio_elegivel_avisa_que_o_proximo_esta_sendo_cavado(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert "proximo--vazio" in pagina
    assert "Ainda cavando o próximo" in pagina
    assert "Três" not in pagina


def test_arquivo_lista_todos_do_mais_recente_ao_mais_antigo_por_mes(projeto):
    _ja_publicado(projeto, "sw-001", "2026-10-30T15:00:00+00:00")
    _ja_publicado(projeto, "sw-002", "2026-11-02T15:00:00+00:00")

    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert pagina.index('id="sw-002"') < pagina.index("Outubro de 2026") < pagina.index('id="sw-001"')
    assert pagina.index("Novembro de 2026") < pagina.index('id="sw-002"')
    assert pagina.count("<audio") == 2
    assert 'href="episodios.html" aria-current="page"' in pagina
    assert 'href="./#sagas"' in pagina


def test_filtro_por_saga_so_aparece_com_mais_de_uma_saga(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    assert 'class="filtro"' not in gerar_pagina_episodios(projeto, "feed.xml")

    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")
    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert 'data-saga="software" aria-pressed="false">Software <span class="filtro__total">1</span>' in pagina
    assert 'data-saga="solucoes" aria-pressed="false">Soluções <span class="filtro__total">1</span>' in pagina


def test_escreve_inicial_e_arquivo(projeto, tmp_path):
    site = tmp_path / "site"
    site.mkdir()

    escrever_pagina(projeto, site, "feed.xml")

    assert (site / "index.html").exists()
    assert (site / "episodios.html").exists()
    assert (site / "sitemap.xml").exists()
    assert (site / "sobre" / "index.html").exists()


def test_etiqueta_mostra_a_saga_e_a_posicao_do_episodio(projeto):
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")

    inicial = gerar_index(projeto, "feed.xml")
    arquivo = gerar_pagina_episodios(projeto, "feed.xml")

    posicao = '<span class="etiqueta__longo">episódio</span><span class="etiqueta__curto">ep.</span> 2 de 3'
    assert 'class="etiqueta__papel">Saga Software' in inicial
    assert posicao in inicial
    assert posicao in arquivo
    assert 'class="amarracao amarracao--verso"' in arquivo
    assert 'class="proximo" data-saga="software"' in inicial


def test_capa_mostra_o_codigo_com_a_sigla_da_saga(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")

    capas = [
        capa
        for pagina in (gerar_index(projeto, "feed.xml"), gerar_pagina_episodios(projeto, "feed.xml"))
        for capa in re.findall(r'<div class="(?:episodio|item|proximo)__capa" aria-hidden="true">(.*?)</div>',
                               pagina, re.DOTALL)
    ]

    codigos = [re.search(r'<span class="codigo__sigla">(\w+)</span>(\d+)', capa).groups() for capa in capas]

    assert len(capas) == 4
    assert {("SW", "001"), ("SL", "001")} <= set(codigos)


def _dados_estruturados(pagina):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', pagina, re.DOTALL).group(1))


def test_paginas_tem_previa_de_compartilhamento_com_imagem(projeto):
    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<meta property="og:image" content="https://x.github.io/pebacast/og.jpg">' in pagina
    assert '<meta property="og:image:width" content="1200">' in pagina
    assert '<meta name="twitter:card" content="summary_large_image">' in pagina
    assert '<link rel="canonical" href="https://x.github.io/pebacast/episodios.html">' in pagina
    assert '<link rel="apple-touch-icon" href="apple-touch-icon.png">' in pagina
    assert '<link rel="icon" href="favicon.ico" sizes="48x48">' in pagina


def test_arquivo_descreve_a_serie_e_os_episodios_para_buscadores(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    serie = _dados_estruturados(gerar_pagina_episodios(projeto, "feed.xml"))

    assert serie["@type"] == "PodcastSeries"
    assert serie["webFeed"] == "https://x.github.io/pebacast/feed.xml"
    [episodio] = serie["episode"]
    assert episodio["url"] == "https://x.github.io/pebacast/episodios/sw-001/"
    assert episodio["timeRequired"] == "PT16M"
    assert episodio["associatedMedia"]["contentUrl"] == "https://cdn/sw-001.mp3"


def test_dados_estruturados_nao_deixam_o_conteudo_fechar_o_script(projeto):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "feed": {**CONFIG["feed"], "titulo": "Peba</script><b>"}})

    pagina = gerar_index(projeto, "feed.xml")

    assert "Peba</script><b>" not in pagina
    assert _dados_estruturados(pagina)["name"] == "Peba</script><b>"


def test_analytics_so_carrega_com_codigo_valido(projeto):
    assert "goatcounter" not in gerar_index(projeto, "feed.xml")

    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"goatcounter": "pebacast"}})
    assert 'data-goatcounter="https://pebacast.goatcounter.com/count"' in gerar_index(projeto, "feed.xml")

    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"goatcounter": 'x" onload="alert(1)'}})
    assert "goatcounter" not in gerar_index(projeto, "feed.xml")


def test_votos_so_aparecem_com_api_https_configurada(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    assert 'class="votos"' not in gerar_index(projeto, "feed.xml")

    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"votos_api": "https://votos.exemplo.dev/"}})
    for pagina in (gerar_index(projeto, "feed.xml"), gerar_pagina_episodios(projeto, "feed.xml")):
        assert 'data-episodio="sw-001" data-api="https://votos.exemplo.dev"' in pagina
        assert pagina.count('class="votos__opcao" type="button" data-voto=') == 2
        assert 'aria-labelledby="votos-sw-001"' in pagina and 'id="votos-sw-001"' in pagina
        assert '<label class="recado__rotulo" for="recado-sw-001">' in pagina and 'id="recado-sw-001"' in pagina
        assert '<form class="recado" id="form-recado-sw-001" data-recado hidden>' in pagina

    for invalida in ("http://votos.exemplo.dev", 'https://x" onload="alert(1)', "javascript:alert(1)"):
        _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"votos_api": invalida}})
        assert 'class="votos"' not in gerar_index(projeto, "feed.xml")


def test_sitemap_lista_as_paginas_com_a_data_do_ultimo_episodio(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    sitemap = gerar_sitemap(projeto)

    assert "<loc>https://x.github.io/pebacast/</loc><lastmod>2026-11-07</lastmod>" in sitemap
    assert "<loc>https://x.github.io/pebacast/episodios.html</loc>" in sitemap
    assert "<loc>https://x.github.io/pebacast/sobre/</loc>" in sitemap


def test_imagem_de_compartilhamento_leva_a_versao_do_conteudo_na_url(projeto):
    (projeto.raiz / "site").mkdir()
    (projeto.raiz / "site" / "og.jpg").write_bytes(b"primeira arte")
    antes = gerar_index(projeto, "feed.xml")

    (projeto.raiz / "site" / "og.jpg").write_bytes(b"arte nova")
    depois = gerar_index(projeto, "feed.xml")

    versao = re.compile(r'<meta property="og:image" content="https://x.github.io/pebacast/og.jpg\?v=([0-9a-f]{8})">')
    assert versao.search(antes).group(1) != versao.search(depois).group(1)


def test_descricao_do_site_cabe_na_previa_das_redes_sociais():
    config = yaml.safe_load((Path(__file__).parent.parent / "config" / "pipeline.yaml").read_text(encoding="utf-8"))

    assert len(" ".join(config["site"]["descricao"].split())) <= 125


# ---------------------------------------------------------------- cor e nome da saga (#10)

CSS = (Path(__file__).resolve().parents[1] / "site" / "estilo.css").read_text(encoding="utf-8")


def test_card_da_secao_sagas_usa_a_cor_da_saga_e_nao_a_posicao(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    for sid in ("software", "solucoes", "sistemas", "dados", "infraestrutura", "seguranca", "corporativa"):
        assert re.search(rf'<li class="saga[^"]*" data-saga="{sid}">', pagina)
    secao_sagas = CSS[CSS.index(".sagas {"):]
    assert not re.search(r"\.saga:nth-child\([^)]*\)\s*\{[^}]*background", secao_sagas)
    assert re.search(r"\.saga \{[^}]*background: var\(--capa-fundo\)", CSS)


def test_voz_convidada_veste_a_cor_da_saga_e_o_apresentador_fica_neutro(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    assert 'class="voz voz--helena" data-saga="software"' in pagina
    assert 'class="voz voz--davi">' in pagina
    assert re.search(r"\.voz\[data-saga\] \{ --chapa: var\(--capa-fundo\); \}", CSS)
    assert not re.search(r"\.voz--[a-z]+\b[^{]*\{", CSS), "nenhuma cor por pessoa no CSS"


def test_voz_convidada_nova_ganha_a_cor_da_saga_sem_css_novo(projeto):
    persona = {"id": "rafael", "nome": "Rafael", "papel": "expert", "sagas": ["sistemas"], "historico": "h"}
    _gravar(projeto.raiz / "curriculum" / "personas" / "rafael.yaml", persona)

    pagina = gerar_index(projeto, "feed.xml")

    assert 'class="voz voz--rafael" data-saga="sistemas"' in pagina
    assert "Voz convidada da saga Sistemas" in pagina


def test_cor_do_apresentador_nao_e_de_nenhuma_saga():
    cores_de_saga = set(re.findall(r'\[data-saga="[a-z]+"\] \{ --capa-fundo: (#[0-9a-f]{6}); \}', CSS))
    neutra = re.search(r"\.voz \{ --chapa: (#[0-9a-f]{6}); \}", CSS).group(1)

    assert len(cores_de_saga) == 7
    assert neutra not in cores_de_saga


def test_site_usa_o_nome_curto_da_saga_em_todo_texto(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    paginas = gerar_index(projeto, "feed.xml") + gerar_pagina_episodios(projeto, "feed.xml")

    assert "Voz convidada da saga Software" in paginas
    assert "Arquitetura de Software" not in paginas


def _luminancia(cor):
    canais = [int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_texto_sobre_as_cores_de_saga_tem_contraste_aa():
    tema = CSS[CSS.index("/* Folheto de cordel"):]
    texto = re.search(r"--texto: (#[0-9a-f]{6})", tema).group(1)
    texto_suave = re.search(r"--texto-suave: (#[0-9a-f]{6})", tema).group(1)
    for cor in re.findall(r'\[data-saga="[a-z]+"\] \{ --capa-fundo: (#[0-9a-f]{6}); \}', CSS):
        for tinta in (texto, texto_suave):
            claro, escuro = sorted((_luminancia(cor), _luminancia(tinta)), reverse=True)
            assert (claro + 0.05) / (escuro + 0.05) >= 4.5, (cor, tinta)


# ---------------------------------------------------------------- saga com endereço (#13)


def test_card_de_saga_no_ar_leva_a_lista_filtrada(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    card = pagina[pagina.index('<li class="saga saga--ativa" data-saga="software">'):]
    card = card[:card.index("</li>")]
    assert '<a class="saga__link" href="episodios.html?saga=software">Software' in card
    assert "Ver episódios" in card


def test_card_de_saga_em_breve_nao_e_link(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert pagina.count('class="saga__link"') == 1
    card = pagina[pagina.index('<li class="saga" data-saga="corporativa">'):]
    card = card[:card.index("</li>")]
    assert "Em breve" in card
    assert "<a " not in card


def test_filtro_tem_um_botao_por_saga_com_o_id_usado_na_url(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")

    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert 'class="filtro__opcao" type="button" data-saga="software" aria-pressed="false"' in pagina
    assert 'class="filtro__opcao" type="button" data-saga="solucoes" aria-pressed="false"' in pagina


def test_filtro_le_e_grava_a_saga_na_url_sem_criar_historico():
    js = (Path(__file__).resolve().parents[1] / "site" / "app.js").read_text(encoding="utf-8")

    assert 'new URLSearchParams(location.search).get("saga")' in js
    assert "history.replaceState" in js
    assert "history.pushState" not in js


# ---------------------------------------------------------------- regra da ordem (#11)


def _com_modo(projeto, modo):
    config = yaml.safe_load((projeto.raiz / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    config["agenda"]["modo"] = modo
    _gravar(projeto.raiz / "config" / "pipeline.yaml", config)


def _passo_da_ordem(pagina):
    inicio = pagina.index("<h3>A vez de cada saga</h3>")
    return pagina[inicio:pagina.index("</li>", inicio)]


def test_no_modo_fila_o_proximo_diz_de_quem_e_a_vez_e_por_que(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert ('<p class="proximo__vez">Agora é a vez da saga Soluções: as sagas se revezam, '
            "e sai a que está há mais tempo sem episódio novo.</p>") in pagina


def test_como_funciona_explica_o_revezamento_e_as_referencias_conferidas(projeto):
    _usar_fila(projeto)

    passo = _passo_da_ordem(gerar_index(projeto, "feed.xml"))

    assert "As sagas se revezam: sai a que está há mais tempo sem episódio novo" in passo
    assert "referências já conferidas no livro" in passo


def test_na_rotacao_semanal_os_textos_falam_da_saga_do_dia(projeto):
    _com_modo(projeto, "rotacao_semanal")

    pagina = gerar_index(projeto, "feed.xml", data=date(2026, 11, 9))  # segunda: software

    assert ("Agora é a vez da saga Software: cada dia da semana é de uma saga, "
            "e o episódio sai na saga do dia.") in pagina
    passo = _passo_da_ordem(pagina)
    assert "Cada dia da semana é de uma saga (segunda Software, terça Soluções," in passo
    assert "sábado Segurança, domingo Corporativa)" in passo
    assert "referências já conferidas no livro" in passo
    assert "se revezam" not in pagina


def test_com_saga_unica_os_textos_falam_de_uma_saga_so(projeto):
    _com_modo(projeto, "saga_unica")

    pagina = gerar_index(projeto, "feed.xml")

    assert "Agora é a vez da saga Software: por enquanto, todos os episódios saem dela, na ordem do currículo." in pagina
    passo = _passo_da_ordem(pagina)
    assert "Por enquanto sai uma saga só, Software, um episódio depois do outro" in passo
    assert "referências já conferidas no livro" in passo
    assert "se revezam" not in pagina


def test_sem_proximo_o_estado_vazio_continua_igual(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert "proximo__vez" not in pagina
    assert ('<p class="proximo__texto">Episódio novo só sai depois que as referências dele são conferidas no livro.\n'
            "          Assim que isso acontecer, ele aparece aqui e chega sozinho no seu app de podcast.</p>") in pagina


# ---------------------------------------------------------------- sobre

CRIADOR = {
    "nome": "Lucas Fernandes",
    "papel": "Desenvolvedor full stack",
    "cidade": "Natal, RN",
    "bio": "Lucas Fernandes é desenvolvedor full stack e criou o Pebacast para estudar arquitetura.",
    "links": [{"rotulo": "GitHub", "url": "https://github.com/lucas-jdev"},
              {"rotulo": "LinkedIn", "url": "https://www.linkedin.com/in/lucas-jdev/"}],
}


def _com_criador(projeto, **criador):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"criador": {**CRIADOR, **criador}}})


def _texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_sobre_responde_o_que_e_e_quem_criou_no_primeiro_paragrafo(projeto):
    _com_criador(projeto)

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    primeiro = _texto(re.search(r'<p class="sobre__definicao">(.*?)</p>', pagina, re.DOTALL).group(1))
    for termo in ("Pebacast", "podcast", "arquitetura", "Lucas Fernandes"):
        assert termo in primeiro
    assert "Software, Soluções, Sistemas, Dados e Informação, Infraestrutura, Segurança e Corporativa" in primeiro


def test_sobre_tem_titulo_descricao_e_canonical_proprios(projeto):
    _com_criador(projeto)

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    titulo = re.search(r"<title>(.*?)</title>", pagina).group(1)
    descricao = re.search(r'<meta name="description" content="(.*?)">', pagina).group(1)
    assert len(titulo) <= 60 and "Sobre" in titulo
    assert len(descricao) <= 155 and "Lucas Fernandes" in descricao
    assert '<link rel="canonical" href="https://x.github.io/pebacast/sobre/">' in pagina


def test_sobre_explica_o_nome_e_que_nao_e_pebcak(projeto):
    pagina = _texto(gerar_pagina_sobre(projeto, "feed.xml"))

    assert "tatu-peba" in pagina
    assert "Não tem relação com PEBCAK" in pagina


def test_quem_faz_mostra_nome_papel_cidade_bio_e_links(projeto):
    _com_criador(projeto, papel="Desenvolvedor full stack · inteligência industrial")

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert '<h3 class="criador__nome">Lucas Fernandes</h3>' in pagina
    assert ('<p class="criador__papel"><span class="criador__parte">Desenvolvedor full stack</span> · '
            '<span class="criador__parte">inteligência industrial</span> · '
            '<span class="criador__parte">Natal, RN</span></p>') in pagina
    assert "criou o Pebacast para estudar arquitetura" in pagina
    assert 'href="https://github.com/lucas-jdev" rel="me noopener">GitHub · lucas-jdev' in pagina
    assert 'href="https://www.linkedin.com/in/lucas-jdev" rel="me noopener">LinkedIn · lucas-jdev' in pagina


def test_sem_bio_quem_faz_mostra_so_nome_e_links(projeto):
    _com_criador(projeto, bio="", papel="", cidade="")

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert 'class="criador__bio"' not in pagina
    assert 'class="criador__papel"' not in pagina
    assert '<h3 class="criador__nome">Lucas Fernandes</h3>' in pagina
    assert 'class="criador__links"' in pagina


def test_sem_criador_configurado_usa_o_autor_do_feed_sem_inventar_nada(projeto):
    pessoa = _dados_estruturados(gerar_index(projeto, "feed.xml"))["author"]

    assert pessoa == {"@type": "Person", "@id": "https://x.github.io/pebacast/sobre/#criador",
                      "name": "Lucas", "url": "https://x.github.io/pebacast/sobre/"}
    assert 'class="criador__links"' not in gerar_pagina_sobre(projeto, "feed.xml")


def test_person_traz_papel_cidade_e_os_links_como_sameas(projeto):
    _com_criador(projeto)

    pessoa = _dados_estruturados(gerar_index(projeto, "feed.xml"))["author"]

    assert pessoa["jobTitle"] == "Desenvolvedor full stack"
    assert pessoa["homeLocation"] == {"@type": "Place", "name": "Natal, RN"}
    assert pessoa["sameAs"] == ["https://github.com/lucas-jdev", "https://www.linkedin.com/in/lucas-jdev"]


def test_link_que_nao_e_https_fica_de_fora_da_pagina_e_do_sameas(projeto):
    _com_criador(projeto, links=[{"rotulo": "X", "url": "javascript:alert(1)"},
                                 {"rotulo": "Y", "url": 'https://a.dev/" onclick="x'},
                                 {"rotulo": "Z", "url": "http://a.dev"}])

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert "sameAs" not in json.dumps(_dados_estruturados(pagina))
    assert "alert(1)" not in pagina and "onclick" not in pagina and "http://a.dev" not in pagina
    assert 'class="criador__links"' not in pagina


def test_todas_as_paginas_ligam_o_podcast_a_mesma_person(projeto):
    _com_criador(projeto)

    inicial = _dados_estruturados(gerar_index(projeto, "feed.xml"))
    arquivo = _dados_estruturados(gerar_pagina_episodios(projeto, "feed.xml"))
    sobre = _dados_estruturados(gerar_pagina_sobre(projeto, "feed.xml"))

    assert sobre["@type"] == "AboutPage"
    assert sobre["mainEntity"]["@id"] == inicial["@id"] == "https://x.github.io/pebacast/#podcast"
    autores = {json.dumps(serie["author"], sort_keys=True) for serie in (inicial, arquivo, sobre["mainEntity"])}
    assert len(autores) == 1


def test_cabecalho_e_rodape_levam_para_sobre_em_todas_as_paginas(projeto):
    inicial = gerar_index(projeto, "feed.xml")
    arquivo = gerar_pagina_episodios(projeto, "feed.xml")
    sobre = gerar_pagina_sobre(projeto, "feed.xml")

    assert '<a href="sobre/">Sobre</a>' in inicial
    assert '<a href="sobre/">Sobre</a>' in arquivo
    assert '<a href="../sobre/" aria-current="page">Sobre</a>' in sobre
    assert '· <a href="sobre/">Lucas</a>' in inicial
    assert '· <a href="../sobre/">Lucas</a>' in sobre


def test_sobre_busca_css_js_e_icones_na_raiz_do_site(projeto):
    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert '<link rel="stylesheet" href="../estilo.css">' in pagina
    assert '<script defer src="../app.js"></script>' in pagina
    assert '<link rel="icon" href="../favicon.ico" sizes="48x48">' in pagina
    assert '<a href="../episodios.html">Episódios</a>' in pagina
    assert '<a href="../#sagas">Sagas</a>' in pagina
    assert '<a class="pular" href="#sobre">Pular para o conteúdo</a>' in pagina
    assert not re.search(r'(?:href|src)="(?:estilo\.css|app\.js|favicon|fontes/)', pagina)


def test_quem_faz_mostra_a_foto_redonda_e_a_person_ganha_image(projeto):
    _com_criador(projeto, foto="criador.jpg")

    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert '<img class="criador__foto" src="../criador.jpg" alt="Foto de Lucas Fernandes"' in pagina
    assert 'class="criador__inicial"' not in pagina
    assert _dados_estruturados(pagina)["mainEntity"]["author"]["image"] == "https://x.github.io/pebacast/criador.jpg"


def test_sem_foto_ou_com_nome_invalido_fica_a_inicial(projeto):
    for foto in ("", "../segredo.jpg", 'x.jpg" onerror="alert(1)', "https://outro.site/foto.jpg"):
        _com_criador(projeto, foto=foto)
        pagina = gerar_pagina_sobre(projeto, "feed.xml")
        assert '<div class="criador__inicial" aria-hidden="true">L</div>' in pagina
        assert "criador__foto" not in pagina and "image" not in _dados_estruturados(pagina)["mainEntity"]["author"]


def test_foto_configurada_existe_no_site():
    raiz = Path(__file__).resolve().parents[1]
    foto = yaml.safe_load((raiz / "config" / "pipeline.yaml").read_text(encoding="utf-8"))["site"]["criador"]["foto"]

    assert (raiz / "site" / foto).is_file()


# ---------------------------------------------------------------- página do episódio


def _tres_publicados(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")


def test_cada_episodio_publicado_ganha_pagina_e_o_resto_nao(projeto, tmp_path):
    _tres_publicados(projeto)
    _escrever_episodio(projeto, "sw-003")
    site = tmp_path / "_site"
    site.mkdir()

    escrever_pagina(projeto, site, "feed.xml")

    assert (site / "episodios" / "sw-001" / "index.html").exists()
    assert (site / "episodios" / "sw-002" / "index.html").exists()
    assert not (site / "episodios" / "sw-003").exists()


def test_pagina_do_episodio_tem_titulo_descricao_e_canonical_proprios(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert "<title>Dois · Saga Software · ep. 2 · Pebacast</title>" in pagina
    assert '<link rel="canonical" href="https://x.github.io/pebacast/episodios/sw-002/">' in pagina
    assert '<h1 class="episodio__titulo">Dois</h1>' in pagina
    assert 'class="player"' in pagina and "Liste dois trade-offs." in pagina


def test_titulos_das_paginas_de_episodio_nao_se_repetem(projeto):
    _tres_publicados(projeto)

    titulos = {re.search(r"<title>(.*?)</title>", gerar_pagina_do_episodio(projeto, "feed.xml", eid)).group(1)
               for eid in ("sw-001", "sw-002")}

    assert len(titulos) == 2


def test_descricao_cabe_no_limite_e_corta_numa_palavra(projeto):
    longo = {**SAGA["episodios"][0], "objetivos": ["Entender " + "acoplamento " * 30]}
    _gravar(projeto.raiz / "curriculum" / "sagas" / "software.yaml", {**SAGA, "episodios": [longo, *SAGA["episodios"][1:]]})
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    descricao = re.search(r'<meta name="description" content="(.*?)">', pagina).group(1)
    assert len(descricao) <= 155
    assert descricao.endswith("acoplamento…")


def test_dados_estruturados_do_episodio_citam_as_fontes_e_ligam_serie_e_criador(projeto):
    _tres_publicados(projeto)

    dados = _dados_estruturados(gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002"))

    assert dados["@type"] == "PodcastEpisode"
    assert dados["url"] == "https://x.github.io/pebacast/episodios/sw-002/"
    assert dados["citation"] == [{"@type": "CreativeWork", "name": "fosa cap. 1"}]
    assert dados["partOfSeries"]["@id"] == "https://x.github.io/pebacast/#podcast"
    assert dados["author"]["@id"] == dados["partOfSeries"]["author"]["@id"] == "https://x.github.io/pebacast/sobre/#criador"


def test_vizinhos_so_ligam_episodios_publicados_da_mesma_saga(projeto):
    _tres_publicados(projeto)
    _escrever_episodio(projeto, "sw-003")

    primeiro = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")
    ultimo = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert 'vizinhos__link--anterior' not in primeiro
    assert 'class="vizinhos__link vizinhos__link--proximo" href="../../episodios/sw-002/"' in primeiro
    assert 'class="vizinhos__link vizinhos__link--anterior" href="../../episodios/sw-001/"' in ultimo
    assert 'vizinhos__link--proximo' not in ultimo


def test_episodio_sozinho_na_saga_nao_tem_navegacao(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    assert 'class="vizinhos"' not in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")


def test_pagina_do_episodio_busca_css_js_e_icones_na_raiz_do_site(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert '<link rel="stylesheet" href="../../estilo.css">' in pagina
    assert '<a href="../../episodios.html">Episódios</a>' in pagina
    assert '<a href="../../episodios.html?saga=software">← Episódios da saga Software</a>' in pagina
    assert not re.search(r'(?:href|src)="(?:estilo\.css|app\.js|favicon|fontes/|\.\./(?!\.\./))', pagina)


def test_listas_levam_a_pagina_do_episodio(projeto):
    _tres_publicados(projeto)

    inicial = gerar_index(projeto, "feed.xml")
    arquivo = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<h3 class="episodio__titulo"><a href="episodios/sw-002/">Dois</a></h3>' in inicial
    assert '<a href="episodios/sw-001/">Um</a></h3>' in arquivo
    assert 'href="episodios/sw-001/">Link deste episódio' in arquivo
    assert 'id="sw-001"' in arquivo, "as âncoras antigas (episodios.html#sw-001) continuam valendo"


def test_sitemap_lista_cada_episodio_com_a_data_de_publicacao(projeto):
    _tres_publicados(projeto)

    sitemap = gerar_sitemap(projeto)

    assert "<url><loc>https://x.github.io/pebacast/episodios/sw-001/</loc><lastmod>2026-11-07</lastmod></url>" in sitemap
    assert "<url><loc>https://x.github.io/pebacast/episodios/sw-002/</loc><lastmod>2026-11-09</lastmod></url>" in sitemap


# ---------------------------------------------------------------- honestidade do processo (#52)


def _site_inteiro(projeto, tmp_path):
    site = tmp_path / "_site"
    site.mkdir(exist_ok=True)
    escrever_pagina(projeto, site, "feed.xml")
    return "\n".join(_texto(p.read_text(encoding="utf-8")) for p in sorted(site.rglob("*.html")))


def test_nenhuma_pagina_promete_revisao_contra_as_fontes(projeto, tmp_path):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    texto = _site_inteiro(projeto, tmp_path)

    for exagero in ("contra as fontes", "contra a fonte", "checadas", "afirmação por afirmação", "caso real,",
                    "Não tem gente"):
        assert exagero not in texto, exagero


def test_como_mostra_as_duas_etapas_humanas_e_quem_faz_cada_uma(projeto):
    _com_criador(projeto)

    pagina = gerar_index(projeto, "feed.xml")

    passos = re.findall(r'<span class="passo__quem passo__quem--(\w+)">([^<]+)</span><h3>([^<]+)</h3>', pagina)
    assert [(papel, titulo) for papel, _, titulo in passos] == [
        ("humano", "Currículo"), ("codigo", "A vez de cada saga"), ("ia", "Caso"), ("ia", "Roteiro"),
        ("ia", "Revisão"), ("codigo", "Voz e feed"), ("humano", "Escuta")]
    assert {quem for papel, quem, _ in passos if papel == "humano"} == {"Humano"}
    assert "depois de publicado" in _texto(pagina).lower()


def test_o_processo_diz_que_ha_gente_mas_nao_quem(projeto):
    _com_criador(projeto)

    como = re.search(r'<section class="secao secao--escura" id="como">.*?</section>', gerar_index(projeto, "feed.xml"),
                     re.DOTALL).group(0)
    sobre_como = re.search(r'id="como-e-feito">.*?</section>', gerar_pagina_sobre(projeto, "feed.xml"), re.DOTALL).group(0)

    assert "Lucas" not in como and "Lucas" not in sobre_como
    assert "curadoria humana" in _texto(como)


def test_numero_de_revisoes_vem_da_configuracao(projeto):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "revisao": {**CONFIG["revisao"], "max_ciclos": 4}})

    assert "São até 5 revisões; se não aprovar, o episódio não sai." in _texto(gerar_index(projeto, "feed.xml"))


def test_selo_diz_quem_revisou_e_leva_ao_relatorio_da_ultima_revisao(projeto):
    roteiro = _roteiro("sw-001")
    _escrever_episodio(projeto, "sw-001", revisoes=[_revisao(roteiro, aprovado=False, veredito="incorreta"),
                                                     _revisao(roteiro)])
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00", reescrever=False)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert "afirmações revisadas por uma 2ª IA, aprovado na 2ª revisão" in pagina
    assert ('href="https://github.com/x/pebacast/blob/main/episodios/sw-001/revisoes/2.json" rel="noopener">'
            "ver o relatório</a>") in pagina


def test_cenario_hipotetico_mostra_a_primeira_frase_e_avisa(projeto):
    _escrever_episodio(projeto, "sw-001", noticia={"tipo": "hipotetico", "cenario":
                       "Uma loja tem três cadastros de clientes. Cada time mantém o seu."})
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00", reescrever=False)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert ('<span class="caso__rotulo">Ponto de partida · cenário hipotético</span>'
            "Uma loja tem três cadastros de clientes.</p>") in pagina
    assert "Cada time mantém o seu" not in pagina


def test_cenario_vazio_nao_mostra_bloco_de_ponto_de_partida(projeto):
    _escrever_episodio(projeto, "sw-001", noticia={"tipo": "hipotetico", "cenario": "  "})
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00", reescrever=False)

    assert 'class="caso"' not in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")


def test_vozes_avisam_que_sao_personagens_ficticios(projeto):
    assert "personagens fictícios" in _texto(gerar_index(projeto, "feed.xml"))


# ---------------------------------------------------------------- beta e canal de opinião (#54)


def _com_beta(projeto, beta=True):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"beta": beta, "votos_api": "https://votos.x.dev"}})


def test_beta_poe_o_carimbo_em_todas_as_paginas_levando_a_sobre(projeto):
    _com_beta(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    assert '<a class="carimbo-beta" href="sobre/#beta"' in gerar_index(projeto, "feed.xml")
    assert '<a class="carimbo-beta" href="sobre/#beta"' in gerar_pagina_episodios(projeto, "feed.xml")
    assert '<a class="carimbo-beta" href="../sobre/#beta"' in gerar_pagina_sobre(projeto, "feed.xml")
    assert '<a class="carimbo-beta" href="../../sobre/#beta"' in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")


def test_beta_explica_na_sobre_e_avisa_do_spotify(projeto):
    _com_beta(projeto)

    sobre = _texto(gerar_pagina_sobre(projeto, "feed.xml"))
    assert "Ainda é beta" in sobre and "O que já é firme" in sobre and "Ainda não está no Spotify" in sobre
    assert "as fontes de cada episódio são escolhidas e conferidas à mão" in sobre
    assert "No Spotify em breve; por enquanto, pelo feed." in _texto(gerar_index(projeto, "feed.xml"))


def test_sem_beta_nada_fala_em_beta_mas_o_fala_comigo_fica(projeto, tmp_path):
    _com_beta(projeto, beta=False)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    texto = _site_inteiro(projeto, tmp_path)

    assert "beta" not in texto.lower() and "Spotify em breve" not in texto
    assert "Fala comigo" in texto


def test_beta_nunca_aparece_no_card_do_episodio(projeto):
    _com_beta(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    artigo = re.search(r"<article.*?</article>", pagina, re.DOTALL).group(0)
    assert "beta" not in artigo.lower()
    assert "beta" not in re.search(r"<title>(.*?)</title>", pagina).group(1).lower()


def test_fala_comigo_leva_aos_formularios_de_issue(projeto):
    pagina = gerar_pagina_sobre(projeto, "feed.xml")

    assert 'href="https://github.com/x/pebacast/issues/new?template=1-ideia.yml"' in pagina
    assert 'href="https://github.com/x/pebacast/issues/new?template=2-bug.yml"' in pagina


def test_recado_tem_botao_proprio_sem_precisar_votar(projeto):
    _com_beta(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert ('<button class="votos__recado" type="button" data-abrir-recado aria-expanded="false"\n'
            '        aria-controls="form-recado-sw-001">Deixar um recado</button>') in pagina
    assert '<form class="recado" id="form-recado-sw-001" data-recado hidden>' in pagina
    assert 'data-repositorio>Repositório</a>' in pagina
