"""Teto por página da captura dos prints (#136, scripts/prints.py): uma página que trava o renderer
falha rápido, com página, viewport e lado, e uma que trava só uma vez sai na nova tentativa.
Abre um Chromium de verdade: sem Playwright ou sem o navegador instalado, os testes são pulados.

Fica separado de test_prints_navegador.py porque `capturar` usa a API assíncrona do Playwright
(asyncio.run), que não roda enquanto o navegador síncrono daquele módulo está aberto."""

import asyncio
import importlib.util
import inspect
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

async_api = pytest.importorskip("playwright.async_api")

_ARQUIVO = Path(__file__).resolve().parents[1] / "scripts" / "prints.py"
_spec = importlib.util.spec_from_file_location("prints_teto", _ARQUIVO)
prints = importlib.util.module_from_spec(_spec)
sys.modules["prints_teto"] = prints
_spec.loader.exec_module(prints)

# Um laço síncrono no evento de rolagem prende a thread principal do renderer: nem setTimeout nem
# requestAnimationFrame disparam mais, como no runner do #136, e os tetos em JS do _JS_PREPARAR não ajudam.
TRAVA_O_RENDERER = '<script>addEventListener("scroll", () => { while (true) {} });</script>'
PAGINA = ('<!doctype html><html><body><header>topo</header>'
          '<section id="s1" style="height:2400px">um</section>{}</body></html>')
TETO_TESTE_S = 10


def _site(tmp_path: Path, trava: bool) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(PAGINA.format(TRAVA_O_RENDERER if trava else ""), encoding="utf-8")
    return site


@pytest.fixture(scope="module")
def chromium():
    async def abrir_e_fechar():
        async with async_api.async_playwright() as p:
            await (await p.chromium.launch()).close()

    try:
        asyncio.run(abrir_e_fechar())
    except Exception as erro:
        pytest.skip(f"Chromium indisponível: {erro}")


def test_o_teto_padrao_e_de_um_minuto_por_pagina_com_uma_nova_tentativa():
    assert prints.TETO_PAGINA_S == 60
    assert prints.TENTATIVAS == 2
    assert inspect.signature(prints.capturar).parameters["teto_s"].default == prints.TETO_PAGINA_S


def test_pagina_que_trava_o_renderer_falha_logo_com_pagina_viewport_e_lado(chromium, tmp_path):
    diagnostico = tmp_path / "diagnostico"

    inicio = time.monotonic()
    with pytest.raises(prints.PaginaTravou) as erro:
        prints.capturar(_site(tmp_path, trava=True), tmp_path / "capturas", ["index"], lado="depois",
                        teto_s=TETO_TESTE_S, diagnostico=diagnostico)
    duracao = time.monotonic() - inicio

    # Duas tentativas de 10 s e dois navegadores abertos: longe dos 6 min do passo.
    assert duracao < 90
    mensagem = str(erro.value)
    assert "página index.html" in mensagem
    assert "viewport desktop (1280x900)" in mensagem
    assert "lado depois" in mensagem
    assert "preparando" in mensagem
    for tentativa in (1, 2):
        nome = f"travou--depois--desktop--index--tentativa-{tentativa}"
        assert (diagnostico / f"{nome}.zip").stat().st_size > 0
        assert "lado depois" in (diagnostico / f"{nome}.txt").read_text(encoding="utf-8")


def test_a_cli_sai_com_erro_e_a_mensagem_no_stderr(chromium, tmp_path, monkeypatch, capfd):
    monkeypatch.setattr(prints, "capturar", partial(prints.capturar, teto_s=TETO_TESTE_S))

    codigo = prints.main(["capturar", "--site", str(_site(tmp_path, trava=True)), "--saida", str(tmp_path / "c"),
                          "--lado", "antes"])

    assert codigo == 1
    assert "Captura abortada: página index.html, viewport desktop (1280x900), lado antes" in capfd.readouterr().err


def test_pagina_que_trava_so_na_primeira_vez_sai_na_segunda_tentativa(chromium, tmp_path, monkeypatch):
    pedidos: list[str] = []

    def servidor_que_trava_uma_vez(pasta: Path) -> ThreadingHTTPServer:
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(pasta), **kwargs)

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/index.html":
                    pedidos.append(self.path)
                    if len(pedidos) == 1:
                        corpo = PAGINA.format(TRAVA_O_RENDERER).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(corpo)))
                        self.end_headers()
                        self.wfile.write(corpo)
                        return
                super().do_GET()

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        return servidor

    monkeypatch.setattr(prints, "_servidor", servidor_que_trava_uma_vez)
    diagnostico = tmp_path / "diagnostico"

    gerados = prints.capturar(_site(tmp_path, trava=False), tmp_path / "capturas", ["index"], lado="antes",
                              teto_s=TETO_TESTE_S, diagnostico=diagnostico)

    assert sorted(arquivo.name for arquivo in gerados) == [
        "index--cabecalho--celular.png", "index--cabecalho--desktop.png",
        "index--s1--celular.png", "index--s1--desktop.png"]
    assert all(arquivo.stat().st_size > 0 for arquivo in gerados)
    assert len(pedidos) == 3  # desktop duas vezes, celular uma
    # Só o estouro deixa rastro: a nova tentativa e a outra tela passaram e não gravam nada.
    assert sorted(p.name for p in diagnostico.iterdir()) == [
        "travou--antes--desktop--index--tentativa-1.txt", "travou--antes--desktop--index--tentativa-1.zip"]


def test_sem_estouro_nada_vai_para_o_diagnostico(chromium, tmp_path):
    diagnostico = tmp_path / "diagnostico"

    gerados = prints.capturar(_site(tmp_path, trava=False), tmp_path / "capturas", ["index"], lado="antes",
                              diagnostico=diagnostico)

    assert len(gerados) == 4
    assert not diagnostico.exists()
