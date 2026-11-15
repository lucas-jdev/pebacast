import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from podcast.audio import Audio, Trechos, concatenar, exportar_mp3
from podcast.qualidade_audio import IncidentesDeAudio, Limites, Medicao, avaliar, maior_pausa, medir, silencios

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fora do PATH")
TAXA = 24_000
LIMITES = Limites()


def _tom(segundos: float, amplitude: float = 0.3, frequencia: float = 440.0) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * frequencia * np.arange(int(TAXA * segundos)) / TAXA)


def _ruido(segundos: float, amplitude: float) -> np.ndarray:
    return amplitude * np.random.default_rng(3).uniform(-1, 1, int(TAXA * segundos))


def _mp3_cru(destino: Path, amostras: np.ndarray) -> Path:
    """MP3 sem passar pela montagem: o áudio chega ao QA do jeito que foi gerado."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(TAXA), "-ac", "1", "-i", "pipe:0",
         "-b:a", "64k", str(destino)],
        input=Audio.de_float(amostras, TAXA).pcm, check=True,
    )
    return destino


def _medida(laudo, nome: str):
    return next(medida for medida in laudo.medidas if medida.nome == nome)


def _laudo(mp3: Path, trechos: Trechos):
    return avaliar(medir(mp3, trechos, LIMITES), LIMITES)


def _so_fala(segundos: float) -> Trechos:
    return Trechos(fala=(0.0, segundos))


# Pico real: ≤ −1,0 dBTP


def test_pico_abaixo_do_limite_passa(tmp_path):
    mp3 = _mp3_cru(tmp_path / "a.mp3", _tom(3, amplitude=0.5))

    assert _medida(_laudo(mp3, _so_fala(3)), "Pico real").aprovada


def test_pico_perto_do_0_dbfs_reprova(tmp_path):
    mp3 = _mp3_cru(tmp_path / "a.mp3", _tom(3, amplitude=0.99))

    medida = _medida(_laudo(mp3, _so_fala(3)), "Pico real")
    assert not medida.aprovada
    assert medida.valor.endswith("dBTP")


# Loudness integrada: −16 LUFS ± 1


def test_loudness_no_alvo_passa(tmp_path):
    mp3 = tmp_path / "a.mp3"
    exportar_mp3(Audio.de_float(_tom(5), TAXA), mp3, bitrate_kbps=64)

    assert _medida(_laudo(mp3, _so_fala(5)), "Loudness integrada").aprovada


def test_loudness_baixa_demais_reprova(tmp_path):
    mp3 = _mp3_cru(tmp_path / "a.mp3", _tom(5, amplitude=0.05))

    assert not _medida(_laudo(mp3, _so_fala(5)), "Loudness integrada").aprovada


@pytest.mark.parametrize(("loudness", "aprovada"), [(-17.0, True), (-15.0, True), (-17.2, False), (-14.8, False)])
def test_tolerancia_da_loudness_vale_nos_dois_sentidos(loudness, aprovada):
    medicao = Medicao(-3.0, loudness, loudness, None, None, 0.3, 1)

    assert _medida(avaliar(medicao, LIMITES), "Loudness integrada").aprovada is aprovada


# Música (abertura e encerramento): não passa a fala


def _episodio_com_musica(destino: Path, amplitude_musica: float) -> tuple[Path, Trechos]:
    musica = _ruido(3, amplitude_musica)
    _mp3_cru(destino, np.concatenate([musica, _tom(5, amplitude=0.3), musica]))
    return destino, Trechos(fala=(3.0, 8.0), abertura=(0.0, 3.0), encerramento=(8.0, 11.0))


def test_musica_mais_baixa_que_a_fala_passa(tmp_path):
    medida = _medida(_laudo(*_episodio_com_musica(tmp_path / "a.mp3", 0.05)), "Música (abertura e encerramento)")

    assert medida.aprovada
    assert "abertura" in medida.valor and "encerramento" in medida.valor


def test_musica_mais_alta_que_a_fala_reprova(tmp_path):
    medida = _medida(_laudo(*_episodio_com_musica(tmp_path / "a.mp3", 0.9)), "Música (abertura e encerramento)")

    assert not medida.aprovada


def test_so_o_encerramento_alto_ja_reprova():
    medicao = Medicao(-2.0, -16.0, -16.0, -20.0, -15.5, 0.3, 1)

    assert not _medida(avaliar(medicao, LIMITES), "Música (abertura e encerramento)").aprovada


def test_sem_vinheta_a_musica_nao_reprova():
    medicao = Medicao(-2.0, -16.0, -16.0, None, None, 0.3, 1)

    medida = _medida(avaliar(medicao, LIMITES), "Música (abertura e encerramento)")
    assert medida.aprovada and medida.valor == "sem vinheta"


# Pausa na troca de blocos: ≤ 0,6 s


def _dois_blocos(destino: Path, pausa_ms: int) -> tuple[Path, Trechos]:
    audio = concatenar([Audio.de_float(_tom(2), TAXA), Audio.de_float(_tom(2), TAXA)], pausa_ms=pausa_ms)
    trechos = exportar_mp3(audio, destino, bitrate_kbps=64)
    return destino, trechos


def test_pausa_curta_na_troca_de_blocos_passa(tmp_path):
    medida = _medida(_laudo(*_dois_blocos(tmp_path / "a.mp3", 300)), "Pausa na troca de blocos")

    assert medida.aprovada
    assert medida.valor.startswith("0,3")


def test_pausa_longa_na_troca_de_blocos_reprova(tmp_path):
    medida = _medida(_laudo(*_dois_blocos(tmp_path / "a.mp3", 1000)), "Pausa na troca de blocos")

    assert not medida.aprovada
    assert medida.valor.startswith("1,0")


def test_pausa_longa_dentro_do_bloco_nao_conta(tmp_path):
    # A pausa de 1 s é do TTS, no meio do bloco; a troca fica na pausa curta.
    amostras = np.concatenate([_tom(1), np.zeros(TAXA), _tom(1), np.zeros(TAXA * 3 // 10), _tom(1)])
    mp3 = _mp3_cru(tmp_path / "a.mp3", amostras)

    medida = _medida(_laudo(mp3, Trechos(fala=(0.0, 4.3), trocas_s=(3.15,))), "Pausa na troca de blocos")

    assert medida.aprovada


def test_silencios_vem_em_segundos_do_episodio_mesmo_com_a_fala_depois_da_abertura(tmp_path):
    amostras = np.concatenate([_tom(1), np.zeros(TAXA), _tom(1), np.zeros(TAXA * 3 // 10), _tom(1)])
    mp3 = _mp3_cru(tmp_path / "a.mp3", amostras)

    assert silencios(mp3, (2.5, 4.3), -50) == [(pytest.approx(3.0, abs=0.01), pytest.approx(3.3, abs=0.01))]


def test_maior_pausa_considera_so_o_silencio_que_contem_a_troca():
    silencios = [(1.0, 2.0), (3.0, 3.3), (5.0, 5.8)]

    assert maior_pausa([3.15, 5.4], silencios) == pytest.approx(0.8)
    assert maior_pausa([], silencios) == 0.0
    assert maior_pausa([4.0], silencios) == 0.0


# Limites e laudo


def test_limites_vem_da_config_e_partem_do_alvo_da_montagem():
    assert Limites.de_config({}) == Limites(loudness_lufs=-16.0, tolerancia_lu=1.0, pico_maximo_dbtp=-1.0,
                                            musica_acima_da_fala_lu=0.0, pausa_maxima_s=0.6)
    assert Limites.de_config({"qualidade": {"pausa_maxima_s": 0.8}}).pausa_maxima_s == 0.8


def test_config_do_projeto_traz_os_limites_da_issue():
    import yaml

    config = yaml.safe_load((Path(__file__).parents[1] / "config" / "pipeline.yaml").read_text(encoding="utf-8"))

    assert Limites.de_config(config["audio"]) == Limites()


def test_laudo_em_markdown_tem_as_quatro_medidas_com_resultado():
    laudo = avaliar(Medicao(0.3, -16.5, -16.5, -16.6, -14.2, 1.1, 4), LIMITES)

    texto = laudo.markdown("Qualidade do áudio do sw-002")

    assert texto.startswith("### Qualidade do áudio do sw-002: reprovado")
    assert texto.count("| aprovado |") == 1 and texto.count("| reprovado |") == 3
    for trecho in ("0,3 dBTP", "-16,5 LUFS", "encerramento -14,2", "1,10 s (4 trocas)"):
        assert trecho in texto


def test_medicao_vai_e_volta_em_json():
    medicao = Medicao(-1.6, -16.0, -16.1, -19.0, None, 0.42, 3)

    assert Medicao.de_json(medicao.para_json()) == medicao


# Issue de incidente


class GhFalso:
    """Responde ao `gh issue list` com as issues abertas e grava os outros comandos."""

    def __init__(self, abertas: list[dict] | None = None) -> None:
        self.abertas = abertas or []
        self.comandos: list[list[str]] = []

    def __call__(self, comando, **_):
        self.comandos.append(comando)
        saida = json.dumps(self.abertas) if comando[1:3] == ["issue", "list"] else ""
        return subprocess.CompletedProcess(comando, 0, stdout=saida)

    def acoes(self) -> list[list[str]]:
        return [comando for comando in self.comandos if comando[1:3] != ["issue", "list"]]


REPROVADO = avaliar(Medicao(0.3, -16.5, -16.5, -16.6, -14.2, 1.1, 4), LIMITES)
APROVADO = avaliar(Medicao(-1.6, -16.0, -16.0, -19.0, -18.5, 0.36, 4), LIMITES)
TITULO = "Áudio do sw-002 fora do padrão"


def test_audio_reprovado_abre_issue_incidente_com_as_medidas():
    gh = GhFalso()

    IncidentesDeAudio("dono/repo", "https://run/1", gh).registrar("sw-002", REPROVADO)

    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"]
    assert criar[criar.index("--title") + 1] == TITULO
    assert criar[criar.index("--label") + 1] == "incidente"
    corpo = criar[criar.index("--body") + 1]
    assert "0,3 dBTP" in corpo and "https://run/1" in corpo and "fecha sozinha" in corpo
    assert criar[-2:] == ["--repo", "dono/repo"]


def test_audio_reprovado_de_novo_comenta_na_issue_aberta_sem_duplicar():
    gh = GhFalso([{"number": 42, "title": TITULO}])

    IncidentesDeAudio("dono/repo", None, gh).registrar("sw-002", REPROVADO)

    [comentar] = gh.acoes()
    assert comentar[:4] == ["gh", "issue", "comment", "42"]


def test_audio_aprovado_fecha_a_issue_do_episodio():
    gh = GhFalso([{"number": 42, "title": TITULO}, {"number": 7, "title": "Roteiro reprovado: sw-002"}])

    IncidentesDeAudio("dono/repo", None, gh).registrar("sw-002", APROVADO)

    [fechar] = gh.acoes()
    assert fechar[:4] == ["gh", "issue", "close", "42"]
    assert "passou no QA" in fechar[fechar.index("--comment") + 1]


def test_audio_aprovado_sem_issue_aberta_nao_faz_nada():
    gh = GhFalso()

    IncidentesDeAudio("dono/repo", None, gh).registrar("sw-002", APROVADO)

    assert gh.acoes() == []


def test_titulo_nao_cai_no_padrao_das_issues_que_a_publicacao_fecha():
    assert not IncidentesDeAudio.titulo("sw-002").endswith(": sw-002")
