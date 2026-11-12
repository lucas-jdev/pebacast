import json
import re

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
    assert '<audio controls preload="none" src="' in pagina
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


def _dados_estruturados(pagina):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', pagina, re.DOTALL).group(1))


def test_paginas_tem_previa_de_compartilhamento_com_imagem(projeto):
    pagina = gerar_pagina_episodios(projeto, "feed.xml")

    assert '<meta property="og:image" content="https://x.github.io/pebacast/og.jpg">' in pagina
    assert '<meta property="og:image:width" content="1200">' in pagina
    assert '<meta name="twitter:card" content="summary_large_image">' in pagina
    assert '<link rel="canonical" href="https://x.github.io/pebacast/episodios.html">' in pagina


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


def test_sitemap_lista_as_paginas_com_a_data_do_ultimo_episodio(projeto):
    _ja_publicado(projeto, "sw-001", "2026-11-07T15:00:00+00:00")

    sitemap = gerar_sitemap(projeto)

    assert "<loc>https://x.github.io/pebacast/</loc><lastmod>2026-11-07</lastmod>" in sitemap
    assert "<loc>https://x.github.io/pebacast/episodios.html</loc>" in sitemap
