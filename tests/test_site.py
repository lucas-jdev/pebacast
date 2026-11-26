import json
import re
from datetime import date
from pathlib import Path

import pytest
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
    assert 'href="episodios/sw-002/" data-compartilhar="sw-002">Compartilhar' in pagina


def test_proximo_segue_a_fila_da_pipeline(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_index(projeto, "feed.xml")

    assert pagina.count('class="proximo__titulo"') == 1
    assert 'class="proximo__titulo">sl-001<' in pagina
    assert "É o próximo da fila: as fontes já foram conferidas" in pagina
    assert "roteiro é o próximo a ser escrito" not in pagina  # vocabulário da pipeline (#120)


def test_roteiro_aprovado_e_o_proximo_mesmo_fora_da_ordem(projeto):
    _escrever_episodio(projeto, "sw-001")

    pagina = gerar_index(projeto, "feed.xml")

    assert 'class="proximo__titulo">Um<' in pagina
    assert "Já está escrito e revisado: sai na próxima publicação." in pagina



def test_roteiro_aguardando_a_cota_avisa_que_sai_em_breve(projeto):
    _escrever_episodio(projeto, "sw-001")
    (projeto.episodios / "sw-001" / "aguardando_cota.json").write_text('{"desde": "2026-11-08T01:00:00+00:00"}\n',
                                                                       encoding="utf-8")

    pagina = gerar_index(projeto, "feed.xml")

    assert 'class="proximo__titulo">Um<' in pagina
    assert ("Tivemos um problema interno ao gravar a voz deste episódio. "
            "O roteiro já está pronto, e ele sai em breve.") in pagina
    assert "Já está escrito e revisado" not in pagina

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

    assert 'data-saga="software" data-nome="Software" aria-pressed="false">Software <span class="filtro__total">1</span>' in pagina
    assert 'data-saga="solucoes" data-nome="Soluções" aria-pressed="false">Soluções <span class="filtro__total">1</span>' in pagina


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

    assert 'class="filtro__opcao" type="button" data-saga="software" data-nome="Software" aria-pressed="false"' in pagina
    assert 'class="filtro__opcao" type="button" data-saga="solucoes" data-nome="Soluções" aria-pressed="false"' in pagina


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
    inicio = pagina.index(" A vez de cada saga</h3>")
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
    assert '<h1 class="episodio__titulo" id="titulo-sw-002">Dois</h1>' in pagina
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
    assert 'href="../../episodios/sw-003/"' not in ultimo, "o sw-003 não foi publicado"


def test_sem_proximo_publicado_diz_qual_e_o_proximo_do_curriculo_e_convida_a_assinar(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = _texto(gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001"))

    assert "O ep. 2 da saga Software, Dois" in pagina
    assert "ainda não saiu. As sagas se revezam, então pode levar alguns dias." in pagina
    assert "Anterior" not in pagina
    assert "Enquanto isso" not in pagina, "só há episódio da própria saga"


def test_proximo_que_nao_saiu_oferece_o_mais_recente_de_outra_saga(projeto):
    # Sem beco sem saída (#120): quem chegou ao fim do que saiu da saga ganha outra coisa para ouvir.
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert ('Enquanto isso, comece a saga Soluções:<a href="../../episodios/sl-001/">sl-001</a>') in pagina


def test_ultimo_episodio_do_curriculo_diz_que_a_saga_acabou(projeto):
    _tres_publicados(projeto)
    _ja_publicado(projeto, "sw-003", "2026-11-10T15:00:00+00:00")

    pagina = _texto(gerar_pagina_do_episodio(projeto, "feed.xml", "sw-003"))

    assert "Este é o último episódio da saga Software no currículo." in pagina


def test_pagina_do_episodio_busca_css_js_e_icones_na_raiz_do_site(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert '<link rel="stylesheet" href="../../estilo.css">' in pagina
    assert '<a href="../../episodios.html" aria-current="true">Episódios</a>' in pagina
    assert '<a href="../../episodios.html?saga=software">← Episódios da saga Software</a>' in pagina
    assert not re.search(r'(?:href|src)="(?:estilo\.css|app\.js|favicon|fontes/|\.\./(?!\.\./))', pagina)


def test_listas_levam_a_pagina_do_episodio(projeto):
    _tres_publicados(projeto)

    inicial = gerar_index(projeto, "feed.xml")
    arquivo = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<h3 class="episodio__titulo" id="titulo-sw-002"><a href="episodios/sw-002/">Dois</a></h3>' in inicial
    assert '<a href="episodios/sw-001/">Um</a></h3>' in arquivo
    assert 'href="episodios/sw-001/" data-compartilhar="sw-001">Compartilhar' in arquivo
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

    passos = re.findall(r'<li class="passo passo--(\w+)"><h3><span class="passo__num">(\d)</span> ([^<]+)</h3>'
                        r'<span class="passo__quem passo__quem--\1"><span class="so-leitor">Quem faz: </span>([^<]+)</span>',
                        pagina)
    assert [(papel, int(n), titulo) for papel, n, titulo, _ in passos] == [
        ("humano", 1, "Currículo"), ("codigo", 2, "A vez de cada saga"), ("ia", 3, "Caso"), ("ia", 4, "Roteiro"),
        ("ia", 5, "Revisão"), ("codigo", 6, "Voz e feed"), ("humano", 7, "Escuta")]
    assert {quem for papel, _, _, quem in passos if papel == "humano"} == {"Humano"}
    assert "depois de publicado" in _texto(pagina).lower()


def test_a_regra_da_revisao_e_carimbada_no_proprio_passo(projeto):
    _com_criador(projeto)

    pagina = gerar_index(projeto, "feed.xml")

    revisao = re.search(r'<li class="passo passo--ia"><h3><span class="passo__num">5</span> Revisão</h3>.*?</li>',
                        pagina, re.DOTALL).group(0)
    assert '<p class="carimbo-regra"><strong class="so-leitor">Regra: </strong>Reprovou' in revisao
    assert pagina.count('class="carimbo-regra"') == 1
    assert '<ol class="cordao" role="list">' in pagina and "não vira episódio" not in pagina


def test_o_processo_diz_que_ha_gente_mas_nao_quem(projeto):
    _com_criador(projeto)

    como = re.search(r'<section class="secao secao--escura" id="como">.*?</section>', gerar_index(projeto, "feed.xml"),
                     re.DOTALL).group(0)
    sobre_como = re.search(r'id="como-e-feito">.*?</section>', gerar_pagina_sobre(projeto, "feed.xml"), re.DOTALL).group(0)

    assert "Lucas" not in como and "Lucas" not in sobre_como
    assert "curadoria humana" in _texto(como)


def test_numero_de_revisoes_vem_da_configuracao(projeto):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "revisao": {**CONFIG["revisao"], "max_ciclos": 4}})

    texto = _texto(gerar_index(projeto, "feed.xml"))
    assert "São até 5 revisões." in texto and "Reprovou 5 vezes? Não sai hoje." in texto


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


def _com_spotify(projeto, url, beta=True):
    _gravar(projeto.raiz / "config" / "pipeline.yaml",
            {**CONFIG, "site": {"beta": beta, "votos_api": "https://votos.x.dev", "spotify": url}})


def test_com_o_spotify_a_assinatura_comeca_por_ele_e_o_em_breve_some(projeto):
    _com_spotify(projeto, "https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz")

    index = gerar_index(projeto, "feed.xml")
    assert '<a class="botao" href="https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz">Ouvir no Spotify</a>' in index
    assert "Spotify em breve" not in _texto(index)
    assert "Ainda não está no Spotify" not in _texto(gerar_pagina_sobre(projeto, "feed.xml"))


def test_icone_do_spotify_entra_so_com_o_arquivo_oficial_colocado(projeto):
    # Marca não se redesenha: o ícone vem do kit do Spotify, posto à mão em site/icones/spotify.svg.
    _com_spotify(projeto, "https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz")
    assert "botao__marca" not in gerar_index(projeto, "feed.xml")

    icone = projeto.raiz / "site" / "icones" / "spotify.svg"
    icone.parent.mkdir(parents=True)
    icone.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")

    assert ('<a class="botao" href="https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz"><img class="botao__marca" '
            'src="icones/spotify.svg" alt="" width="20" height="20">Ouvir no Spotify</a>') in gerar_index(projeto, "feed.xml")


def test_com_o_spotify_a_serie_aponta_para_ele_no_sameas(projeto):
    _com_spotify(projeto, "https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz?si=abc")

    assert '"sameAs":["https://open.spotify.com/show/5EMHP24shu7Y7fhfRbLkUz"]' in gerar_index(projeto, "feed.xml")


@pytest.mark.parametrize("url", ["http://open.spotify.com/show/abc", "https://evil.example/show/abc",
                                 'https://open.spotify.com/show/abc"onmouseover=x', "https://open.spotify.com/episode/abc"])
def test_link_do_spotify_fora_do_formato_e_ignorado(projeto, url):
    _com_spotify(projeto, url)

    index = gerar_index(projeto, "feed.xml")
    assert "Ouvir no Spotify" not in index and "open.spotify.com" not in index
    assert "No Spotify em breve; por enquanto, pelo feed." in _texto(index)


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


# ---------------------------------------------------------------- página do episódio e player (#53, #56)


def test_pagina_do_episodio_se_apresenta_e_leva_a_sobre(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert '<p class="apresenta"><strong>Pebacast</strong> · podcast diário de arquitetura em diálogo' in pagina
    assert '<a href="../../sobre/">O que é →</a>' in pagina


def test_pre_requisito_da_mesma_saga_nao_repete_o_caminho_do_anterior(projeto):
    # #120: "continua SW 001" ao lado de "Anterior: SW 002" parecia dizer que a pessoa pulou um episódio.
    _tres_publicados(projeto)
    _ja_publicado(projeto, "sw-003", "2026-11-10T15:00:00+00:00")

    for episodio in ("sw-001", "sw-002", "sw-003"):
        assert 'class="antes"' not in gerar_pagina_do_episodio(projeto, "feed.xml", episodio)


def test_pre_requisito_de_outra_saga_continua_avisado(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    saga = yaml.safe_load((projeto.raiz / "curriculum" / "sagas" / "solucoes.yaml").read_text(encoding="utf-8"))
    saga["episodios"][0]["pre_requisitos"] = ["sw-001"]
    (projeto.raiz / "curriculum" / "sagas" / "solucoes.yaml").write_text(yaml.safe_dump(saga, allow_unicode=True), encoding="utf-8")
    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sl-001")

    assert '<p class="antes">Este episódio continua <a href="../../episodios/sw-001/">Um</a>.' in pagina


def test_arquivo_traz_o_proximo_de_cada_saga_escondido_e_o_titulo_que_o_filtro_troca(projeto):
    _usar_fila(projeto)
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    _ja_publicado(projeto, "sl-001", "2026-11-08T15:00:00+00:00")

    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<h1 class="secao__titulo" data-arquivo-titulo>Todos os episódios</h1>' in pagina
    assert 'data-saga="software" data-nome="Software"' in pagina
    assert re.search(r'<p class="arquivo__proximo" data-proximo-da-saga="software" hidden>Próximo da saga: '
                     r'<strong>Dois</strong>, o ep\. 2,', pagina)
    assert '<p class="arquivo__proximo" data-proximo-da-saga="solucoes" hidden>' in pagina


def test_pre_requisito_que_nao_saiu_nao_vira_link(projeto):
    _ja_publicado(projeto, "sw-002", "2026-11-09T15:00:00+00:00")

    assert 'class="antes"' not in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")


def test_titulos_da_pagina_do_episodio_nao_pulam_nivel(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    niveis = [int(n) for n in re.findall(r"<h([1-6])[ >]", pagina)]
    assert niveis[0] == 1
    assert all(depois - antes <= 1 for antes, depois in zip(niveis, niveis[1:])), niveis


def test_cada_player_tem_o_nome_do_episodio(projeto):
    _tres_publicados(projeto)

    for pagina in (gerar_index(projeto, "feed.xml"), gerar_pagina_episodios(projeto, "feed.xml"),
                   gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")):
        for eid in re.findall(r'<div class="player" role="group" aria-labelledby="titulo-([\w-]+)"', pagina):
            assert f'id="titulo-{eid}"' in pagina
        assert 'data-player-aviso' in pagina


def test_volume_de_cada_player_controla_o_proprio_painel(projeto):
    _tres_publicados(projeto)

    for pagina in (gerar_index(projeto, "feed.xml"), gerar_pagina_episodios(projeto, "feed.xml"),
                   gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")):
        paineis = re.findall(r'aria-controls="(volume-[\w-]+)"', pagina)
        assert paineis and len(paineis) == len(set(paineis))
        for painel in paineis:
            assert re.search(rf'id="{painel}" hidden>\s*<input class="player__nivel" type="range"', pagina)
        assert 'id="i-volume"' in pagina and 'id="i-mudo"' in pagina


def test_onde_o_ouvinte_parou_nasce_escondido_e_so_o_js_mostra(projeto):
    # Sem JS (ou sem nada salvo), nada de "Você parou em" nem de selo vazio (#111).
    _tres_publicados(projeto)

    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    players = re.findall(r'<div class="player" [^>]*data-episodio="([\w-]+)"', pagina)
    assert players and pagina.count('<p class="player__retomar" data-retomar hidden>') == len(players)
    for eid in players:
        assert f'<span class="progresso" data-progresso="{eid}" hidden></span>' in pagina


def test_player_tem_pular_com_nome_acessivel_e_dados_para_a_tela_de_bloqueio(projeto):
    # #117: −15/+30 com nome que diz a direção, e título e saga para o Media Session.
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert '<button class="player__pular" type="button" data-pular="-15" aria-label="Voltar 15 segundos">' in pagina
    assert '<button class="player__pular" type="button" data-pular="30" aria-label="Avançar 30 segundos">' in pagina
    assert re.search(r'data-episodio="sw-002"\s+data-titulo="Dois" data-rotulo="Saga Software · ep. 2"', pagina)


# ---------------------------------------------------------------- transcrição e acabamento (#55, #57)


def test_transcricao_fica_so_na_pagina_do_episodio(projeto):
    _tres_publicados(projeto)
    fala = _roteiro("sw-002")["falas"][1]["texto"]

    inicial = gerar_index(projeto, "feed.xml")
    arquivo = gerar_pagina_episodios(projeto, "feed.xml")
    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert fala in pagina
    assert fala not in inicial and fala not in arquivo
    assert 'class="transcricao' not in inicial and 'class="transcricao' not in arquivo
    assert '<a class="dobra dobra--link" href="episodios/sw-002/#transcricao">Transcrição' in inicial
    assert '<a class="dobra dobra--link" href="episodios/sw-001/#transcricao">Transcrição' in arquivo


def test_transcricao_da_pagina_e_leitura_corrida_com_ancora(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")

    assert '<details class="dobra" id="transcricao">' in pagina
    assert 'class="transcricao transcricao--corrida"' in pagina
    assert re.search(r"\.transcricao--corrida \{ max-height: none; overflow: visible; max-width: 66ch;", CSS)


def test_ancoras_antigas_do_arquivo_continuam_existindo(projeto):
    _tres_publicados(projeto)

    arquivo = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<li class="item" id="sw-001"' in arquivo and '<li class="item" id="sw-002"' in arquivo


def test_pagina_do_episodio_marca_o_card_para_o_titulo_vencer_o_codigo(projeto):
    _tres_publicados(projeto)

    assert 'class="episodio episodio--destaque episodio--pagina"' in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")
    assert "episodio--pagina" not in gerar_index(projeto, "feed.xml")
    assert re.search(r"\.episodio--pagina h1\.episodio__titulo \{ font-size: clamp\(2\.2rem", CSS)


def test_play_vem_antes_do_ponto_de_partida_so_na_pagina_do_episodio(projeto):
    _tres_publicados(projeto)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-002")
    inicial = gerar_index(projeto, "feed.xml")

    assert pagina.index('class="player"') < pagina.index('class="caso"')
    assert inicial.index('class="caso"') < inicial.index('class="player"')


def test_theme_color_e_um_so_e_bate_com_o_fundo(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    assert pagina.count('name="theme-color"') == 1
    assert '<meta name="theme-color" content="#efe4c8">' in pagina


def test_vozes_tem_botao_para_ler_a_historia(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    assert '<button class="voz__mais" type="button" aria-expanded="false" aria-controls="historico-davi">' in pagina
    assert 'id="historico-davi"' in pagina


def test_titulos_sem_viuvas_e_campo_do_feed_com_altura_no_celular():
    assert "h1, h2, h3 { text-wrap: balance; }" in CSS
    assert "@media (max-width: 420px) { .feed__linha { flex-direction: column; } .feed__url { flex: none; } }" in CSS


def test_endereco_do_feed_quebra_depois_das_barras_sem_separador_solto(projeto):
    _tres_publicados(projeto)

    pagina = gerar_index(projeto, "feed.xml")

    assert '<code id="url-feed" class="feed__url">https://x.github.io/<wbr>pebacast/<wbr>feed.xml</code>' in pagina
    links_do_feed = pagina.split('<p class="feed__extra">')[1].split("</p>")[0]
    assert "·" not in links_do_feed


# ---------------------------------------------------------------- desafio para iniciantes (#58)


def test_desafio_iniciante_aparece_dentro_do_desafio(projeto):
    roteiro = {**_roteiro("sw-001"), "desafio_iniciante": "Abra o site.py do Pebacast e aponte o acoplamento."}
    _escrever_episodio(projeto, "sw-001", roteiro=roteiro, revisoes=[_revisao(roteiro)])
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00", reescrever=False)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert ('<p class="desafio__iniciante"><strong>Ainda não trabalha na área?</strong> '
            "Abra o site.py do Pebacast e aponte o acoplamento.</p>") in pagina


def test_caminho_no_desafio_quebra_entre_as_pastas(projeto):
    roteiro = {**_roteiro("sw-001"), "desafio_iniciante": "Abra .github/workflows/publicar.yml no Pebacast."}
    _escrever_episodio(projeto, "sw-001", roteiro=roteiro, revisoes=[_revisao(roteiro)])
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00", reescrever=False)

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert "Abra .github/<wbr>workflows/<wbr>publicar.yml no Pebacast.</p>" in pagina


def test_roteiro_sem_desafio_iniciante_nao_mostra_nada(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    assert "desafio__iniciante" not in gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")


def test_previa_de_compartilhamento_le_os_objetivos_como_frases(projeto):
    # #118: os objetivos juntos sem pontuação liam "…do STRIDE Relacionar…" na prévia do WhatsApp.
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")
    saga = yaml.safe_load((projeto.raiz / "curriculum" / "sagas" / "software.yaml").read_text(encoding="utf-8"))
    saga["episodios"][0]["objetivos"] = ["Aplicar o STRIDE", "Relacionar ameaça e controle."]
    (projeto.raiz / "curriculum" / "sagas" / "software.yaml").write_text(yaml.safe_dump(saga, allow_unicode=True), encoding="utf-8")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert '<meta property="og:description" content="Aplicar o STRIDE. Relacionar ameaça e controle.">' in pagina


def test_player_diz_de_onde_vem_a_retomada(projeto):
    # O JS troca "Você parou em" por "O link começa em" quando a página abre com ?t= (#118).
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    pagina = gerar_pagina_do_episodio(projeto, "feed.xml", "sw-001")

    assert '<span data-retomar-motivo>Você parou em</span> <span data-retomar-tempo></span>' in pagina
