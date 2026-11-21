"""Comparação, manifesto, validação do artefato e comentário dos prints (scripts/prints.py).
Nenhum teste abre navegador: as imagens são matrizes numpy e os PNG são só bytes com a assinatura."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

_ARQUIVO = Path(__file__).resolve().parents[1] / "scripts" / "prints.py"
_spec = importlib.util.spec_from_file_location("prints", _ARQUIVO)
prints = importlib.util.module_from_spec(_spec)
sys.modules["prints"] = prints
_spec.loader.exec_module(prints)

SHA = "0123456789abcdef0123456789abcdef01234567"
PNG_FALSO = prints.ASSINATURA_PNG + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 32


def _imagem(cor: int, altura: int = 40, largura: int = 60) -> np.ndarray:
    return np.full((altura, largura, 4), cor, dtype=np.uint8)


def _capturas(pasta: Path, imagens: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Grava PNGs falsos com o nome da captura e devolve o que o carregador deve ler de cada um."""
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = {}
    for nome, matriz in imagens.items():
        arquivo = pasta / nome
        arquivo.write_bytes(PNG_FALSO + nome.encode())
        conteudo[str(arquivo)] = matriz
    return conteudo


def _comparar(tmp_path: Path, antes: dict, depois: dict, pr: int = 7) -> dict:
    lido = _capturas(tmp_path / "antes", antes) | _capturas(tmp_path / "depois", depois)
    return prints.comparar(tmp_path / "antes", tmp_path / "depois", tmp_path / "artefato", pr,
                           carregar=lambda arquivo: lido[str(arquivo)])


def _artefato(pasta: Path, manifesto: dict, arquivos: dict[str, bytes] | None = None) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "manifesto.json").write_text(json.dumps(manifesto), encoding="utf-8")
    if arquivos is None:
        arquivos = {prints.nome_imagem(item, lado): PNG_FALSO
                    for item in manifesto["itens"] for lado in prints.lados(item["estado"])}
    for nome, conteudo in arquivos.items():
        (pasta / nome).write_bytes(conteudo)
    return pasta


ALTERADA = {"pagina": "index", "secao": "inicio", "tela": "desktop", "estado": "alterada"}
NOVA = {"pagina": "episodios", "secao": "arquivo", "tela": "celular", "estado": "nova"}
REMOVIDA = {"pagina": "index", "secao": "vozes", "tela": "celular", "estado": "removida"}


class TestNomeDasSecoes:
    def test_cabecalho_e_rodape_da_pagina_e_secoes_por_id_ou_rotulo(self):
        elementos = [
            {"indice": 0, "tag": "header", "id": "", "rotulo": ""},
            {"indice": 1, "tag": "section", "id": "inicio", "rotulo": ""},
            {"indice": 2, "tag": "section", "id": "", "rotulo": "mes-1"},
            {"indice": 3, "tag": "section", "id": "", "rotulo": ""},
            {"indice": 4, "tag": "footer", "id": "", "rotulo": ""},
        ]
        assert prints.nomear_secoes(elementos) == [
            (0, "cabecalho"), (1, "inicio"), (2, "mes-1"), (3, "secao-3"), (4, "rodape")]

    def test_header_dentro_de_secao_nao_vira_print_e_invisivel_e_pulado(self):
        elementos = [
            {"indice": 0, "tag": "section", "id": "a", "rotulo": ""},
            {"indice": 1, "tag": "header", "id": "", "rotulo": "", "dentro_de_secao": True},
            {"indice": 2, "tag": "section", "id": "oculta", "rotulo": "", "visivel": False},
        ]
        assert prints.nomear_secoes(elementos) == [(0, "a")]

    def test_nome_normalizado_e_repetido_ganha_sufixo(self):
        elementos = [
            {"indice": 0, "tag": "section", "id": "Próximo Episódio", "rotulo": ""},
            {"indice": 1, "tag": "section", "id": "proximo-episodio", "rotulo": ""},
            {"indice": 2, "tag": "section", "id": "../../x", "rotulo": ""},
        ]
        assert prints.nomear_secoes(elementos) == [(0, "proximo-episodio"), (1, "proximo-episodio-2"), (2, "x")]


class TestComparacao:
    def test_imagens_iguais_nao_mudaram(self):
        assert not prints.imagens_diferentes(_imagem(100), _imagem(100))

    def test_ruido_de_antialiasing_fica_dentro_da_tolerancia(self):
        depois = _imagem(100)
        depois[0, :prints.MAX_PIXELS_DIFERENTES] = 140
        depois[1:, :] = 100 + prints.LIMIAR_CANAL
        assert not prints.imagens_diferentes(_imagem(100), depois)

    def test_mancha_de_cor_pequena_mudou(self):
        # 7x7 px: o miolo 5x5 é liso nos dois lados, 25 pixels acima do limite de 16.
        depois = _imagem(100)
        depois[10:17, 10:17] = 140
        assert prints.imagens_diferentes(_imagem(100), depois)

    def test_linha_de_1_px_com_pouco_contraste_passa(self):
        # Decisão do #75: fina e de pouco contraste é indistinguível de antialiasing.
        depois = _imagem(100)
        depois[20, 5:55] = 140
        assert not prints.imagens_diferentes(_imagem(100), depois)

    def test_linha_de_1_px_com_contraste_forte_mudou(self):
        depois = _imagem(100)
        depois[20, 5:55] = 255
        assert prints.imagens_diferentes(_imagem(100), depois)

    def test_tamanho_diferente_mudou(self):
        assert prints.imagens_diferentes(_imagem(100), _imagem(100, altura=41))


def _trocar_fundo(imagem: np.ndarray, cor: tuple[int, int, int]) -> np.ndarray:
    """Troca a cor do fundo e mantém o texto: cada pixel é tinta misturada ao fundo, e só a parte
    de fundo da mistura muda de cor."""
    pixels = imagem.astype(np.float64)
    brilho = pixels.mean(axis=2)
    fundo = np.median(pixels.reshape(-1, 3), axis=0)
    tinta, claro = brilho.min(), fundo.mean()
    parte_de_fundo = np.clip((brilho - tinta) / (claro - tinta), 0, 1)[..., None]
    return np.clip(pixels + parte_de_fundo * (np.array(cor) - fundo), 0, 255).round().astype(np.uint8)


@pytest.fixture(scope="module")
def recorte() -> tuple[np.ndarray, np.ndarray]:
    """Recorte de 400x110 px do parágrafo de index·inicio no desktop, das capturas do PR #72 (branch
    `prints`, pr-72/index--inicio--desktop--{antes,depois}.png, caixa 615,415 a 1015,525). O texto é o
    mesmo; o antes saiu com antialiasing subpixel e o depois em tons de cinza. Em .npz para o teste não
    depender do Pillow, que fica no extra `prints`."""
    with np.load(Path(__file__).parent / "fixtures" / "prints" / "recorte-pr72.npz") as dados:
        return dados["antes"], dados["depois"]


class TestRuidoDeRenderizacao:
    def test_a_regra_antiga_marcava_o_recorte_como_alterado(self, recorte):
        antes, depois = recorte
        diferenca = np.abs(antes.astype(np.int16) - depois.astype(np.int16)).max(axis=2)
        assert (diferenca > prints.LIMIAR_CANAL).sum() == 8440

    def test_so_antialiasing_diferente_nao_mudou(self, recorte):
        assert not prints.imagens_diferentes(*recorte)

    @pytest.mark.parametrize("destino,origem", [
        # "minutos", na 1ª linha, vira "episódio", copiado da 2ª linha.
        ((slice(4, 34), slice(238, 324)), (slice(39, 69), slice(284, 370))),
        # "de", na 1ª linha, vira "há", copiado da 3ª linha.
        ((slice(4, 34), slice(148, 172)), (slice(73, 103), slice(136, 160))),
    ], ids=["minutos-por-episodio", "de-por-ha"])
    def test_palavra_trocada_num_paragrafo_mudou(self, recorte, destino, origem):
        antes, depois = recorte
        trocado = depois.copy()
        trocado[destino] = depois[origem]
        assert prints.imagens_diferentes(antes, trocado)
        assert prints.imagens_diferentes(depois, trocado)

    # O recorte é do tamanho de um card. O fundo dele é o --fundo do tema (#efe4c8); as trocas vão
    # para o --fundo-2 do tema e para o fundo da seção alternada, o tom mais próximo da paleta.
    @pytest.mark.parametrize("cor", [(0xe6, 0xd6, 0xb0), (0xf3, 0xea, 0xd2)], ids=["e6d6b0", "f3ead2"])
    def test_fundo_do_card_trocado_mudou(self, recorte, cor):
        antes, depois = recorte
        assert prints.imagens_diferentes(antes, _trocar_fundo(depois, cor))


class TestManifesto:
    def test_so_os_pares_que_mudaram_vao_para_o_artefato(self, tmp_path):
        manifesto = _comparar(
            tmp_path,
            antes={"index--inicio--desktop.png": _imagem(10), "index--sagas--desktop.png": _imagem(50)},
            depois={"index--inicio--desktop.png": _imagem(200), "index--sagas--desktop.png": _imagem(50)},
        )
        assert manifesto == {"pr": 7, "itens": [ALTERADA]}
        artefato = tmp_path / "artefato"
        assert sorted(p.name for p in artefato.iterdir()) == [
            "index--inicio--desktop--antes.png", "index--inicio--desktop--depois.png", "manifesto.json"]
        assert json.loads((artefato / "manifesto.json").read_text(encoding="utf-8")) == manifesto

    def test_secao_nova_so_tem_depois_e_removida_so_antes(self, tmp_path):
        manifesto = _comparar(
            tmp_path,
            antes={"index--vozes--celular.png": _imagem(1)},
            depois={"episodios--arquivo--celular.png": _imagem(1)},
        )
        assert manifesto["itens"] == [REMOVIDA, NOVA]
        assert sorted(p.name for p in (tmp_path / "artefato").glob("*.png")) == [
            "episodios--arquivo--celular--depois.png", "index--vozes--celular--antes.png"]

    def test_sem_diferenca_gera_manifesto_vazio_que_passa_na_validacao(self, tmp_path):
        manifesto = _comparar(tmp_path, {"index--inicio--desktop.png": _imagem(9)},
                              {"index--inicio--desktop.png": _imagem(9)})
        assert manifesto["itens"] == []
        assert prints.validar(tmp_path / "artefato") == {"pr": 7, "itens": []}

    def test_desktop_antes_do_celular_e_index_antes_de_episodios(self, tmp_path):
        nomes = ["episodios--arquivo--desktop.png", "index--inicio--celular.png", "index--inicio--desktop.png"]
        manifesto = _comparar(tmp_path, {}, {n: _imagem(1) for n in nomes})
        assert [(i["pagina"], i["tela"]) for i in manifesto["itens"]] == [
            ("index", "desktop"), ("episodios", "desktop"), ("index", "celular")]


class TestValidacao:
    def test_artefato_valido_devolve_o_manifesto(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 42, "itens": [ALTERADA, NOVA, REMOVIDA]})
        assert prints.validar(pasta) == {"pr": 42, "itens": [ALTERADA, NOVA, REMOVIDA]}

    @pytest.mark.parametrize("nome", ["leia.txt", "index--inicio--desktop--antes.png.sh", "script.js"])
    def test_arquivo_que_nao_e_png_nem_manifesto_recusa_tudo(self, tmp_path, nome):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [ALTERADA]})
        (pasta / nome).write_bytes(b"x")
        with pytest.raises(prints.ArtefatoInvalido):
            prints.validar(pasta)

    def test_extensao_png_sem_assinatura_png_e_recusada(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [NOVA]},
                          {"episodios--arquivo--celular--depois.png": b"<script>alert(1)</script>"})
        with pytest.raises(prints.ArtefatoInvalido, match="não é PNG"):
            prints.validar(pasta)

    def test_subpasta_e_recusada(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": []})
        (pasta / "sub").mkdir()
        with pytest.raises(prints.ArtefatoInvalido):
            prints.validar(pasta)

    def test_imagem_que_o_manifesto_nao_cita_e_recusada(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": []}, {"index--inicio--desktop--antes.png": PNG_FALSO})
        with pytest.raises(prints.ArtefatoInvalido, match="não batem"):
            prints.validar(pasta)

    def test_imagem_citada_que_falta_e_recusada(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [ALTERADA]},
                          {"index--inicio--desktop--antes.png": PNG_FALSO})
        with pytest.raises(prints.ArtefatoInvalido, match="não batem"):
            prints.validar(pasta)

    def test_manifesto_ausente_e_recusado(self, tmp_path):
        pasta = tmp_path / "a"
        pasta.mkdir()
        (pasta / "index--inicio--desktop--antes.png").write_bytes(PNG_FALSO)
        with pytest.raises(prints.ArtefatoInvalido, match="manifesto ausente"):
            prints.validar(pasta)

    @pytest.mark.parametrize("pr", [0, -3, "12", 12.0, True, None, 10**9])
    def test_numero_do_pr_precisa_ser_inteiro_positivo(self, tmp_path, pr):
        pasta = _artefato(tmp_path / "a", {"pr": pr, "itens": []})
        with pytest.raises(prints.ArtefatoInvalido, match="PR"):
            prints.validar(pasta)

    @pytest.mark.parametrize("item", [
        {**ALTERADA, "secao": "x](https://mal.example)"},
        {**ALTERADA, "pagina": "../etc"},
        {**ALTERADA, "tela": "tablet"},
        {**ALTERADA, "estado": "outro"},
        {**ALTERADA, "extra": "x"},
        {**ALTERADA, "secao": "a" * 65},
    ])
    def test_item_fora_do_formato_e_recusado(self, tmp_path, item):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [item]}, {})
        with pytest.raises(prints.ArtefatoInvalido):
            prints.validar(pasta)

    def test_manifesto_com_campo_a_mais_ou_que_nao_e_json_e_recusado(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [], "comando": "rm"})
        with pytest.raises(prints.ArtefatoInvalido):
            prints.validar(pasta)
        (pasta / "manifesto.json").write_bytes(b"\xff\xfe nao json")
        with pytest.raises(prints.ArtefatoInvalido):
            prints.validar(pasta)

    def test_item_repetido_e_recusado(self, tmp_path):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [ALTERADA, ALTERADA]})
        with pytest.raises(prints.ArtefatoInvalido, match="repetido"):
            prints.validar(pasta)

    def test_limites_de_tamanho_e_quantidade(self, tmp_path, monkeypatch):
        pasta = _artefato(tmp_path / "a", {"pr": 1, "itens": [ALTERADA, NOVA]})
        monkeypatch.setattr(prints, "MAX_IMAGENS", 2)
        with pytest.raises(prints.ArtefatoInvalido, match="imagens demais"):
            prints.validar(pasta)
        monkeypatch.setattr(prints, "MAX_IMAGENS", 80)
        monkeypatch.setattr(prints, "MAX_BYTES_TOTAL", 2 * len(PNG_FALSO))
        with pytest.raises(prints.ArtefatoInvalido, match="grande demais"):
            prints.validar(pasta)
        monkeypatch.setattr(prints, "MAX_BYTES_IMAGEM", len(PNG_FALSO) - 1)
        with pytest.raises(prints.ArtefatoInvalido, match="imagem grande demais"):
            prints.validar(pasta)


class TestPaginas:
    def test_cada_pagina_tem_o_seu_caminho_no_site(self, tmp_path):
        for arquivo in ("index.html", "episodios.html", "sobre/index.html",
                        "episodios/sw-002/index.html", "episodios/co-001/index.html"):
            (tmp_path / arquivo).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / arquivo).write_text("<html></html>")
        assert [prints.caminho_da_pagina(tmp_path, p) for p in prints.PAGINAS] == [
            "index.html", "episodios.html", "sobre/", "episodios/co-001/"]

    def test_pagina_que_nao_existe_nesse_lado_nao_tem_caminho(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        assert prints.caminho_da_pagina(tmp_path, "sobre") is None
        assert prints.caminho_da_pagina(tmp_path, "episodio") is None

    def test_toda_pagina_tem_rotulo_e_cabe_no_nome_do_arquivo(self):
        assert set(prints.ROTULOS) == set(prints.PAGINAS)
        for pagina in prints.PAGINAS:
            assert prints.RE_CAPTURA.match(prints.nome_captura(pagina, "cabecalho", "desktop"))


class TestComentario:
    def test_pagina_nova_aparece_com_o_caminho_no_titulo_do_par(self):
        item = {"pagina": "sobre", "secao": "quem-faz", "tela": "celular", "estado": "nova"}
        corpo = prints.comentario({"pr": 3, "itens": [item]}, "dono/repo", SHA)
        assert "**sobre/ · quem-faz** (nova)" in corpo
        assert "`index.html`, `episodios.html`, `sobre/` e `episodios/<id>/`" in corpo

    def test_tabela_antes_e_depois_separando_desktop_e_celular(self):
        corpo = prints.comentario({"pr": 42, "itens": [ALTERADA, NOVA, REMOVIDA]}, "dono/repo", SHA)
        assert corpo.startswith(prints.MARCADOR)
        base = "https://raw.githubusercontent.com/dono/repo/prints/pr-42/"
        assert corpo.index("### Desktop (1280 px)") < corpo.index("### Celular (390 px)")
        assert f"| ![Antes: inicio]({base}index--inicio--desktop--antes.png?v=0123456" in corpo
        assert f"![Depois: inicio]({base}index--inicio--desktop--depois.png?v=0123456)" in corpo
        assert f"| _seção nova_ | ![Depois: arquivo]({base}episodios--arquivo--celular--depois.png?v=0123456) |" in corpo
        assert f"| ![Antes: vozes]({base}index--vozes--celular--antes.png?v=0123456) | _seção removida_ |" in corpo
        assert corpo.count("| Antes | Depois |") == 3

    def test_so_desktop_nao_mostra_celular(self):
        corpo = prints.comentario({"pr": 1, "itens": [ALTERADA]}, "dono/repo", SHA)
        assert "Celular" not in corpo

    def test_sem_mudanca_diz_que_nada_mudou(self):
        corpo = prints.comentario({"pr": 1, "itens": []}, "dono/repo", SHA)
        assert corpo.startswith(prints.MARCADOR)
        assert "Nenhuma mudança visual nas páginas capturadas" in corpo
        assert "| Antes |" not in corpo

    @pytest.mark.parametrize("repo,sha", [("dono/repo) [x](y", SHA), ("dono/repo", "abc"), ("dono", SHA)])
    def test_repo_e_commit_sao_validados(self, repo, sha):
        with pytest.raises(ValueError):
            prints.comentario({"pr": 1, "itens": []}, repo, sha)

    def test_cli_valida_antes_de_comentar(self, tmp_path, capsys):
        pasta = _artefato(tmp_path / "a", {"pr": 5, "itens": [ALTERADA]})
        assert prints.main(["validar", str(pasta)]) == 0
        assert capsys.readouterr().out.strip() == "5"
        (pasta / "intruso.svg").write_text("<svg/>")
        assert prints.main(["comentario", str(pasta), "--repo", "dono/repo", "--sha", SHA]) == 1
        captura = capsys.readouterr()
        assert captura.out == ""
        assert "Artefato recusado" in captura.err
