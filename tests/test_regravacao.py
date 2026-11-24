import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from podcast.publicacao import GitHubReleases, publicar_pendentes
from podcast.qualidade_audio import IncidentesDeAudio, Medicao
from podcast.regravacao import RegravacaoInvalida, main, regravar, substituir
from tests.conftest import ProvedorFalso, ProvedorQuebrado
from tests.test_publicacao import Gh, _configurar_vinheta
from tests.test_qualidade_audio import GhFalso
from tests.test_roteiro import _escrever_episodio, _gravar, projeto  # noqa: F401 (fixture)

precisa_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fora do PATH")
PUBLICADO = datetime(2026, 11, 9, 22, 0, tzinfo=timezone.utc)
REGRAVADO = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)


class ReleasesFalso:
    """Um release por episódio, guardado em memória como nome do asset -> bytes."""

    def __init__(self) -> None:
        self.assets: dict[str, dict[str, bytes]] = {}

    def publicar(self, episodio_id: str, titulo: str, arquivo: Path) -> str:
        return self.anexar(episodio_id, arquivo)

    def anexar(self, episodio_id: str, arquivo: Path) -> str:
        self.assets.setdefault(episodio_id, {})[arquivo.name] = arquivo.read_bytes()
        return f"https://cdn/{episodio_id}/{arquivo.name}"

    def baixar(self, episodio_id: str, nome: str, pasta: Path) -> Path:
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / nome
        destino.write_bytes(self.assets[episodio_id][nome])
        return destino

    def remover(self, episodio_id: str, nome: str) -> None:
        del self.assets[episodio_id][nome]


def _fabrica(provedor=None):
    criados = []

    def criar(nome: str):
        criados.append(nome)
        return provedor or ProvedorFalso(nome, frequencia_hz=220.0)

    criar.criados = criados
    return criar


def _ja_publicado(projeto, tmp_path, releases: ReleasesFalso) -> dict:
    _escrever_episodio(projeto, "sw-001")
    publicar_pendentes(projeto, releases, lambda nome: ProvedorFalso(nome), tmp_path / "publicacao", lambda: PUBLICADO)
    return _ler_publicacao(projeto)


def _ler_publicacao(projeto) -> dict:
    return json.loads((projeto.episodios / "sw-001" / "publicacao.json").read_text(encoding="utf-8"))


@precisa_ffmpeg
def test_regravar_anexa_candidata_sem_tocar_no_audio_publicado(projeto, tmp_path):
    releases = ReleasesFalso()
    antes = _ja_publicado(projeto, tmp_path, releases)
    publicado = releases.assets["sw-001"]["pebacast-sw-001.mp3"]

    candidata = regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")

    assert candidata.url == "https://cdn/sw-001/pebacast-sw-001-candidata.mp3"
    assert releases.assets["sw-001"]["pebacast-sw-001.mp3"] == publicado
    assert _ler_publicacao(projeto) == antes


@precisa_ffmpeg
def test_substituir_troca_o_audio_e_mantem_url_guid_e_data(projeto, tmp_path):
    releases = ReleasesFalso()
    antes = _ja_publicado(projeto, tmp_path, releases)
    no_ar = releases.assets["sw-001"]["pebacast-sw-001.mp3"]
    regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")
    candidata = releases.assets["sw-001"]["pebacast-sw-001-candidata.mp3"]

    depois = substituir(projeto, "sw-001", releases, tmp_path / "troca", lambda: REGRAVADO).publicacao

    assert releases.assets["sw-001"] == {"pebacast-sw-001.mp3": candidata, "pebacast-sw-001-anterior.mp3": no_ar}
    assert {chave: depois[chave] for chave in ("guid", "url_audio", "publicado_em")} == \
        {chave: antes[chave] for chave in ("guid", "url_audio", "publicado_em")}
    assert depois["tamanho_bytes"] == len(candidata)
    assert depois["regravado_em"] == "2026-11-14T14:00:00+00:00"
    assert depois["tts"] == {"provedor": "gemini-falso", "fallback": False}
    assert _ler_publicacao(projeto) == depois


@precisa_ffmpeg
def test_regravar_nao_cai_no_fallback(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    fabrica = _fabrica(ProvedorQuebrado())

    with pytest.raises(ConnectionError):
        regravar(projeto, "sw-001", releases, fabrica, tmp_path / "trabalho")

    assert fabrica.criados == ["gemini-falso"]
    assert list(releases.assets["sw-001"]) == ["pebacast-sw-001.mp3"]


def test_regravar_recusa_episodio_nao_publicado(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    fabrica = _fabrica()

    with pytest.raises(RegravacaoInvalida, match="ainda não foi publicado"):
        regravar(projeto, "sw-001", ReleasesFalso(), fabrica, tmp_path)

    assert fabrica.criados == []


def test_regravar_recusa_episodio_fora_do_curriculo(projeto, tmp_path):
    with pytest.raises(RegravacaoInvalida, match="não é um episódio do currículo"):
        regravar(projeto, "sw-999", ReleasesFalso(), _fabrica(), tmp_path)


def test_regravar_recusa_roteiro_que_deixou_de_passar_na_validacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001", revisoes=[])
    _gravar(projeto.episodios / "sw-001" / "publicacao.json", {"guid": "pebacast-sw-001"})
    fabrica = _fabrica()

    with pytest.raises(RegravacaoInvalida, match="validação"):
        regravar(projeto, "sw-001", ReleasesFalso(), fabrica, tmp_path)

    assert fabrica.criados == []


def test_regravar_sem_a_vinheta_configurada_falha_em_vez_de_piorar_o_audio(projeto, tmp_path):
    _configurar_vinheta(projeto)
    _escrever_episodio(projeto, "sw-001")
    _gravar(projeto.episodios / "sw-001" / "publicacao.json", {"guid": "pebacast-sw-001", "vinheta": True})
    fabrica = _fabrica()

    with pytest.raises(RegravacaoInvalida, match="vinheta"):
        regravar(projeto, "sw-001", ReleasesFalso(), fabrica, tmp_path)

    assert fabrica.criados == []


def test_cli_explica_o_motivo_e_sai_com_erro(projeto, capsys):
    codigo = main(["--raiz", str(projeto.raiz), "substituir", "sw-001", "--repo", "dono/repo"])

    assert codigo == 1
    assert "ainda não foi publicado" in capsys.readouterr().err


def test_releases_baixa_e_remove_pelo_nome_do_asset(tmp_path):
    gh = Gh(release_existe=True)
    releases = GitHubReleases("lucas-jdev/pebacast", gh)

    baixado = releases.baixar("sw-002", "pebacast-sw-002-candidata.mp3", tmp_path)
    releases.remover("sw-002", "pebacast-sw-002-candidata.mp3")

    assert baixado == tmp_path / "pebacast-sw-002-candidata.mp3"
    assert gh.comandos[0][:6] == ["gh", "release", "download", "episodio-sw-002", "--pattern", "pebacast-sw-002-candidata.mp3"]
    assert gh.comandos[1][:5] == ["gh", "release", "delete-asset", "episodio-sw-002", "pebacast-sw-002-candidata.mp3"]
    assert "--yes" in gh.comandos[1]



@precisa_ffmpeg
def test_regravar_anexa_as_medidas_do_qa_ao_lado_da_candidata(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)

    candidata = regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")

    medicao = Medicao.de_json(releases.assets["sw-001"]["pebacast-sw-001-candidata.qualidade.json"].decode("utf-8"))
    assert medicao.loudness_lufs == pytest.approx(-16, abs=1)
    assert [medida.nome for medida in candidata.laudo.medidas] == [
        "Pico real", "Loudness integrada", "Música (abertura e encerramento)", "Pausa na troca de blocos"]


@precisa_ffmpeg
def test_substituir_por_candidata_que_passa_no_qa_fecha_o_incidente(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")
    gh = GhFalso([{"number": 31, "title": "Áudio do sw-001 fora do padrão"}])

    substituicao = substituir(projeto, "sw-001", releases, tmp_path / "troca", lambda: REGRAVADO,
                              IncidentesDeAudio("dono/repo", None, gh))

    assert substituicao.laudo.aprovado
    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "close", "31"]]
    assert sorted(releases.assets["sw-001"]) == ["pebacast-sw-001-anterior.mp3", "pebacast-sw-001.mp3"]


@precisa_ffmpeg
def test_substituir_por_candidata_reprovada_mantem_o_incidente_aberto(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")
    fora = Medicao(0.3, -16.0, -16.0, None, None, 1.1, 3)
    releases.assets["sw-001"]["pebacast-sw-001-candidata.qualidade.json"] = fora.para_json().encode("utf-8")
    gh = GhFalso([{"number": 31, "title": "Áudio do sw-001 fora do padrão"}])

    substituir(projeto, "sw-001", releases, tmp_path / "troca", lambda: REGRAVADO, IncidentesDeAudio("dono/repo", None, gh))

    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "comment", "31"]]


@precisa_ffmpeg
def test_substituir_candidata_sem_medidas_troca_o_audio_sem_laudo(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho")
    del releases.assets["sw-001"]["pebacast-sw-001-candidata.qualidade.json"]
    gh = GhFalso()

    substituicao = substituir(projeto, "sw-001", releases, tmp_path / "troca", lambda: REGRAVADO,
                              IncidentesDeAudio("dono/repo", None, gh))

    assert substituicao.laudo is None and gh.comandos == []
    assert sorted(releases.assets["sw-001"]) == ["pebacast-sw-001-anterior.mp3", "pebacast-sw-001.mp3"]
