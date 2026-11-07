import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from podcast.publicacao import (
    GitHubReleases,
    episodios_pendentes,
    gerar_feed,
    publicar_pendentes,
    sintetizar_com_fallback,
)
from tests.conftest import ProvedorFalso, ProvedorQuebrado
from tests.test_roteiro import _escrever_episodio, _revisao, _roteiro, projeto  # noqa: F401 (fixture)

precisa_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fora do PATH")
AGORA = datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc)


class StorageFalso:
    def __init__(self) -> None:
        self.publicados: list[tuple[str, str]] = []

    def publicar(self, episodio_id: str, titulo: str, arquivo: Path) -> str:
        assert arquivo.exists()
        self.publicados.append((episodio_id, arquivo.name))
        return f"https://cdn/{arquivo.name}"


def _fabrica(quebrar: set[str] = frozenset()):
    criados = []

    def criar(nome: str):
        criados.append(nome)
        return ProvedorQuebrado() if nome in quebrar else ProvedorFalso(nome)

    criar.criados = criados
    return criar


def _publicar(projeto, tmp_path, fabrica=None, storage=None):
    return publicar_pendentes(projeto, storage or StorageFalso(), fabrica or _fabrica(), tmp_path / "trabalho", lambda: AGORA)


def test_pendentes_sao_pastas_com_roteiro_e_sem_publicacao(projeto):
    _escrever_episodio(projeto, "sw-001")
    _escrever_episodio(projeto, "sw-002")
    (projeto.episodios / "sw-002" / "publicacao.json").write_text("{}", encoding="utf-8")
    (projeto.episodios / "vazia").mkdir()

    assert episodios_pendentes(projeto) == ["sw-001"]


@precisa_ffmpeg
def test_publica_episodio_aprovado(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    storage = StorageFalso()

    resultado = _publicar(projeto, tmp_path, storage=storage)

    assert resultado.publicados == ["sw-001"] and not resultado.reprovados and not resultado.avisos
    assert storage.publicados == [("sw-001", "pebacast-sw-001.mp3")]
    publicacao = json.loads((projeto.episodios / "sw-001" / "publicacao.json").read_text(encoding="utf-8"))
    assert publicacao["guid"] == "pebacast-sw-001"
    assert publicacao["url_audio"] == "https://cdn/pebacast-sw-001.mp3"
    assert publicacao["tts"] == {"provedor": "gemini-falso", "fallback": False}
    assert publicacao["tamanho_bytes"] > 0
    assert publicacao["publicado_em"] == "2026-11-08T01:00:00+00:00"


def test_roteiro_reprovado_nao_gasta_tts_nem_publica(projeto, tmp_path):
    roteiro = _roteiro("sw-001")
    _escrever_episodio(projeto, "sw-001", revisoes=[_revisao(roteiro, aprovado=False, veredito="incorreta")])
    fabrica, storage = _fabrica(), StorageFalso()

    resultado = _publicar(projeto, tmp_path, fabrica, storage)

    assert list(resultado.reprovados) == ["sw-001"]
    assert fabrica.criados == [] and storage.publicados == []
    assert not (projeto.episodios / "sw-001" / "publicacao.json").exists()


def test_pasta_fora_do_curriculo_e_reprovada(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-999")
    assert "nenhum episódio do currículo" in _publicar(projeto, tmp_path).reprovados["sw-999"][0]


@precisa_ffmpeg
def test_fallback_gera_aviso_e_fica_registrado(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")

    resultado = _publicar(projeto, tmp_path, _fabrica(quebrar={"gemini-falso"}))

    assert resultado.publicados == ["sw-001"]
    assert "fallback kokoro-falso" in resultado.avisos[0]
    publicacao = json.loads((projeto.episodios / "sw-001" / "publicacao.json").read_text(encoding="utf-8"))
    assert publicacao["tts"] == {"provedor": "kokoro-falso", "fallback": True}


def test_fallback_tambem_cobre_falha_ao_criar_o_principal(davi):
    def sem_chave():
        raise KeyError("GEMINI_API_KEY")

    _, provedor, erro = sintetizar_com_fallback([], sem_chave, lambda: ProvedorFalso("kokoro"))
    assert provedor == "kokoro" and "GEMINI_API_KEY" in erro


@precisa_ffmpeg
def test_feed_lista_episodios_publicados_com_enclosure_e_guid(projeto, tmp_path):
    noticia = {"tipo": "noticia", "titulo": "Apagão", "url": "https://n/1", "fonte": "Jornal", "data": "2026-11-01",
               "nota_relevancia": 8, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _publicar(projeto, tmp_path)

    canal = ET.fromstring(gerar_feed(projeto)).find("channel")
    itens = canal.findall("item")

    assert canal.find("title").text == "pebacast"
    assert len(itens) == 1
    item = itens[0]
    assert item.find("title").text == "Um"
    assert item.find("guid").text == "pebacast-sw-001"
    assert item.find("guid").get("isPermaLink") == "false"
    assert item.find("enclosure").get("type") == "audio/mpeg"
    assert item.find("pubDate").text == "Sun, 08 Nov 2026 01:00:00 +0000"
    notas = item.find("description").text
    assert "gerado por inteligência artificial" in notas
    assert "Apagão (Jornal, 2026-11-01) https://n/1" in notas
    assert "Desafio: Liste dois trade-offs." in notas


def test_feed_vazio_e_valido(projeto):
    canal = ET.fromstring(gerar_feed(projeto)).find("channel")
    assert canal.findall("item") == []


class Gh:
    def __init__(self, release_existe: bool) -> None:
        self.release_existe = release_existe
        self.comandos: list[list[str]] = []

    def __call__(self, comando, **_):
        self.comandos.append(comando)
        codigo = 0 if comando[2] != "view" or self.release_existe else 1
        return subprocess.CompletedProcess(comando, codigo)


def test_releases_cria_um_release_por_episodio(tmp_path):
    gh = Gh(release_existe=False)
    url = GitHubReleases("lucas-jdev/pebacast", gh).publicar("sw-001", "Tudo é trade-off", tmp_path / "pebacast-sw-001.mp3")

    assert url == "https://github.com/lucas-jdev/pebacast/releases/download/episodio-sw-001/pebacast-sw-001.mp3"
    assert gh.comandos[1][:4] == ["gh", "release", "create", "episodio-sw-001"]


def test_releases_republica_sem_mudar_a_url(tmp_path):
    gh = Gh(release_existe=True)
    url = GitHubReleases("lucas-jdev/pebacast", gh).publicar("sw-001", "t", tmp_path / "pebacast-sw-001.mp3")

    assert url.endswith("/episodio-sw-001/pebacast-sw-001.mp3")
    assert gh.comandos[1][:3] == ["gh", "release", "upload"] and "--clobber" in gh.comandos[1]


def _configurar_vinheta(projeto) -> None:
    import yaml

    arquivo = projeto.raiz / "config" / "pipeline.yaml"
    config = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    config["audio"]["vinheta"] = {"arquivo": "assets/vinheta.mp3", "credito": "Vinheta de Fulano", "sobreposicao_s": 1,
                                  "abertura": {"inicio_s": 0, "duracao_s": 4, "fade_saida_s": 2},
                                  "encerramento": {"inicio_s": 5, "duracao_s": 4, "fade_saida_s": 0}}
    arquivo.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")


@precisa_ffmpeg
def test_vinheta_configurada_entra_no_episodio(projeto, tmp_path):
    _configurar_vinheta(projeto)
    (projeto.raiz / "assets").mkdir()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=10",
                    str(projeto.raiz / "assets" / "vinheta.mp3")], check=True)
    _escrever_episodio(projeto, "sw-001")

    resultado = _publicar(projeto, tmp_path)

    publicacao = json.loads((projeto.episodios / "sw-001" / "publicacao.json").read_text(encoding="utf-8"))
    assert resultado.avisos == [] and publicacao["vinheta"] is True
    assert publicacao["duracao_segundos"] == 1 + 3 + 4  # fala falsa de 1 s, abertura e encerramento
    assert "Vinheta de Fulano" in gerar_feed(projeto)


@precisa_ffmpeg
def test_sem_o_arquivo_decifrado_publica_sem_vinheta_e_avisa(projeto, tmp_path):
    _configurar_vinheta(projeto)
    _escrever_episodio(projeto, "sw-001")

    resultado = _publicar(projeto, tmp_path)

    assert resultado.publicados == ["sw-001"]
    assert "publicado sem vinheta" in resultado.avisos[0] and "VINHETA_SENHA" in resultado.avisos[0]
    assert "Vinheta de Fulano" not in gerar_feed(projeto)  # sem vinheta no áudio, sem crédito
