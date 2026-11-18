import json
import re
from datetime import date
from pathlib import Path

import yaml

from podcast.site import (
    escrever_pagina,
    gerar_index,
    gerar_pagina_episodios,
    gerar_sitemap,
)
from tests.test_publicacao import _publicar
from tests.test_roteiro import (  # noqa: F401 (fixture)
    CONFIG,
    SAGA,
    _escrever_episodio,
    _gravar,
    _usar_fila,
    projeto,
)

SAGA_SEM_EPISODIO_PUBLICADO = {
    **SAGA,
    "id": "corporativa",
    "nome": "Arquitetura Corporativa",
    "episodios": [{**SAGA["episodios"][0], "id": "co-001", "titulo": "Elevador do arquiteto"}],
}


def _ja_publicado(projeto, episodio, publicado_em):
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
    assert 'href="episodios.html#sw-002">Link deste episódio' in pagina


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
    assert episodio["url"] == "https://x.github.io/pebacast/episodios.html#sw-001"
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
        assert '<form class="recado" data-recado hidden>' in pagina

    for invalida in ("http://votos.exemplo.dev", 'https://x" onload="alert(1)', "javascript:alert(1)"):
        _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"votos_api": invalida}})
        assert 'class="votos"' not in gerar_index(projeto, "feed.xml")


def test_sitemap_lista_as_paginas_com_a_data_do_ultimo_episodio(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    sitemap = gerar_sitemap(projeto)

    assert "<loc>https://x.github.io/pebacast/</loc><lastmod>2026-11-07</lastmod>" in sitemap
    assert "<loc>https://x.github.io/pebacast/episodios.html</loc>" in sitemap


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
