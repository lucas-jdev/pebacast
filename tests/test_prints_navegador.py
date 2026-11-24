"""A preparação da página antes dos prints nunca pode esperar para sempre (scripts/prints.py).
Abre um Chromium de verdade: sem Playwright ou sem o navegador instalado, os testes são pulados."""

import importlib.util
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

_ARQUIVO = Path(__file__).resolve().parents[1] / "scripts" / "prints.py"
_spec = importlib.util.spec_from_file_location("prints_navegador", _ARQUIVO)
prints = importlib.util.module_from_spec(_spec)
sys.modules["prints_navegador"] = prints
_spec.loader.exec_module(prints)

TRAVAS = {
    "quadro que nunca é pintado": "window.requestAnimationFrame = () => 0;",
    "fontes que nunca ficam prontas": "Object.defineProperty(document, 'fonts', {value: {ready: new Promise(() => {})}});",
    "imagem que nunca decodifica": "HTMLImageElement.prototype.decode = () => new Promise(() => {});",
}


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception as erro:
            pytest.skip(f"Chromium indisponível: {erro}")
        yield chromium
        chromium.close()


@pytest.mark.parametrize("trava", TRAVAS.values(), ids=TRAVAS.keys())
def test_preparar_termina_mesmo_com_espera_que_nunca_resolve(navegador, trava):
    pagina = navegador.new_page(viewport={"width": 400, "height": 300})
    pagina.add_init_script(trava)
    html = '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw="><div style="height:900px"></div>'
    pagina.route("http://prints.teste/", lambda rota: rota.fulfill(content_type="text/html", body=html))
    pagina.goto("http://prints.teste/")

    inicio = time.monotonic()
    pagina.evaluate(prints._JS_PREPARAR, [50, 200])

    assert time.monotonic() - inicio < 5
    pagina.close()
