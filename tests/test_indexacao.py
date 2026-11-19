import json
from datetime import date

from podcast.indexacao import (
    API_INDEXNOW,
    avisar,
    chave_indexnow,
    corpo_do_aviso,
    escrever_chave,
    urls_para_avisar,
)
from podcast.publicacao import escrever_site
from podcast.site import gerar_index, gerar_pagina_episodios
from tests.test_roteiro import CONFIG, _gravar, projeto  # noqa: F401 (fixture)

CHAVE = "a1b2c3d4e5f6a7b8"
BASE = "https://x.github.io/pebacast/"
SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<url><loc>{BASE}</loc><lastmod>2026-11-19</lastmod></url>"
    f"<url><loc>{BASE}episodios.html</loc><lastmod>2026-11-19</lastmod></url>"
    f"<url><loc>{BASE}episodios/sw-001/</loc><lastmod>2026-11-02</lastmod></url>"
    f"<url><loc>{BASE}sobre/</loc></url>"
    "</urlset>\n"
)
HOJE = date(2026, 11, 19)


def _com_chave(projeto, chave=CHAVE):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"indexnow": chave}})


def _site_com_sitemap(tmp_path, sitemap=SITEMAP):
    site = tmp_path / "_site"
    site.mkdir(exist_ok=True)
    (site / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    return site


class EnvioFalso:
    def __init__(self, status=202, erro=None):
        self.status, self.erro, self.pedidos = status, erro, []

    def __call__(self, url, corpo):
        self.pedidos.append((url, json.loads(corpo)))
        if self.erro:
            raise self.erro
        return self.status


def test_chave_so_vale_no_formato_do_protocolo():
    assert chave_indexnow({"site": {"indexnow": CHAVE}}) == CHAVE
    for invalida in ("", "curta", "com espaço 12345", "x" * 129, "../../etc/passwd"):
        assert chave_indexnow({"site": {"indexnow": invalida}}) is None
    assert chave_indexnow({}) is None


def test_site_publica_a_chave_num_arquivo_com_o_proprio_nome(projeto, tmp_path):
    _com_chave(projeto)

    escrever_site(projeto, tmp_path / "_site")

    assert (tmp_path / "_site" / f"{CHAVE}.txt").read_text(encoding="utf-8") == CHAVE


def test_sem_chave_nenhum_arquivo_e_publicado(projeto, tmp_path):
    assert escrever_chave(projeto.config(), tmp_path) is None
    assert list(tmp_path.glob("*.txt")) == []


def test_avisa_so_o_que_mudou_na_janela():
    assert urls_para_avisar(SITEMAP, HOJE) == [BASE, f"{BASE}episodios.html"]
    assert urls_para_avisar(SITEMAP, HOJE, dias=20) == [BASE, f"{BASE}episodios.html", f"{BASE}episodios/sw-001/"]


def test_todas_inclui_as_urls_sem_lastmod():
    assert urls_para_avisar(SITEMAP, HOJE, todas=True) == [
        BASE, f"{BASE}episodios.html", f"{BASE}episodios/sw-001/", f"{BASE}sobre/"]


def test_chave_fica_na_subpasta_e_so_vao_urls_de_dentro_dela():
    corpo = corpo_do_aviso(BASE, CHAVE, [BASE, "https://x.github.io/outro/", f"{BASE}sobre/"])

    assert corpo == {"host": "x.github.io", "key": CHAVE, "keyLocation": f"{BASE}{CHAVE}.txt",
                     "urlList": [BASE, f"{BASE}sobre/"]}


def test_avisa_o_indexnow_e_registra_as_urls_no_log(projeto, tmp_path):
    _com_chave(projeto)
    envio = EnvioFalso(202)

    linha = avisar(projeto, _site_com_sitemap(tmp_path), hoje=HOJE, enviar=envio)

    [(url, corpo)] = envio.pedidos
    assert url == API_INDEXNOW
    assert corpo["urlList"] == [BASE, f"{BASE}episodios.html"]
    assert linha.startswith("IndexNow: 202, 2 URL(s) avisada(s)")


def test_sem_chave_nao_avisa_ninguem(projeto, tmp_path):
    envio = EnvioFalso()

    linha = avisar(projeto, _site_com_sitemap(tmp_path), hoje=HOJE, enviar=envio)

    assert envio.pedidos == []
    assert "sem chave" in linha


def test_nada_mudou_na_janela_nao_avisa(projeto, tmp_path):
    _com_chave(projeto)
    envio = EnvioFalso()

    linha = avisar(projeto, _site_com_sitemap(tmp_path), hoje=date(2026, 12, 31), enviar=envio)

    assert envio.pedidos == []
    assert "nenhuma URL mudou" in linha


def test_resposta_de_erro_vira_aviso_e_nao_excecao(projeto, tmp_path):
    _com_chave(projeto)

    linha = avisar(projeto, _site_com_sitemap(tmp_path), hoje=HOJE, enviar=EnvioFalso(403))

    assert linha.startswith("::warning::IndexNow respondeu 403")


def test_falha_de_rede_vira_aviso_e_nao_excecao(projeto, tmp_path):
    _com_chave(projeto)

    linha = avisar(projeto, _site_com_sitemap(tmp_path), hoje=HOJE, enviar=EnvioFalso(erro=OSError("sem rede")))

    assert linha.startswith("::warning::IndexNow: falha de rede")


def test_sitemap_ausente_ou_quebrado_vira_aviso(projeto, tmp_path):
    _com_chave(projeto)
    vazio = tmp_path / "vazio"
    vazio.mkdir()

    assert avisar(projeto, vazio, hoje=HOJE, enviar=EnvioFalso()).startswith("::warning::")
    assert avisar(projeto, _site_com_sitemap(tmp_path, "<urlset"), hoje=HOJE,
                  enviar=EnvioFalso()).startswith("::warning::")


def test_meta_de_verificacao_so_aparece_com_codigo_valido(projeto):
    assert "google-site-verification" not in gerar_index(projeto, "feed.xml")
    assert "msvalidate.01" not in gerar_index(projeto, "feed.xml")

    _gravar(projeto.raiz / "config" / "pipeline.yaml",
            {**CONFIG, "site": {"verificacao": {"google": "AbC_123-xyz987", "bing": "0A1B2C3D4E5F"}}})
    for pagina in (gerar_index(projeto, "feed.xml"), gerar_pagina_episodios(projeto, "feed.xml")):
        assert '<meta name="google-site-verification" content="AbC_123-xyz987">' in pagina
        assert '<meta name="msvalidate.01" content="0A1B2C3D4E5F">' in pagina

    _gravar(projeto.raiz / "config" / "pipeline.yaml",
            {**CONFIG, "site": {"verificacao": {"google": 'x" onload="alert(1)', "bing": ""}}})
    pagina = gerar_index(projeto, "feed.xml")
    assert "google-site-verification" not in pagina and "msvalidate.01" not in pagina
