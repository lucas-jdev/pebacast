import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from podcast.audio import Audio, Recorte, Vinheta, concatenar, duracao_mp3, exportar_mp3


def test_concatenar_insere_pausa_entre_as_partes():
    parte = Audio.silencio(100, 24_000)

    resultado = concatenar([parte, parte, parte], pausa_ms=50)

    assert resultado.duracao_segundos == pytest.approx(0.4)


def test_concatenar_recusa_taxas_de_amostragem_diferentes():
    with pytest.raises(ValueError, match="Taxas de amostragem diferentes"):
        concatenar([Audio.silencio(100, 24_000), Audio.silencio(100, 22_050)])


def test_concatenar_recusa_lista_vazia():
    with pytest.raises(ValueError):
        concatenar([])


def test_de_float_limita_amostras_fora_do_intervalo():
    audio = Audio.de_float(np.array([2.0, -2.0]), 24_000)

    assert np.frombuffer(audio.pcm, dtype="<i2").tolist() == [32767, -32767]


def test_exportar_mp3_gera_arquivo_mono_na_taxa_de_saida(tmp_path):
    tempo = np.arange(22_050) / 22_050
    audio = Audio.de_float(0.3 * np.sin(2 * np.pi * 440 * tempo), 22_050)
    destino = tmp_path / "saida.mp3"

    exportar_mp3(audio, destino, bitrate_kbps=64)

    sonda = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(destino)],
        capture_output=True, check=True, text=True,
    )
    stream = json.loads(sonda.stdout)["streams"][0]
    assert stream["channels"] == 1
    assert stream["sample_rate"] == "24000"
    assert float(stream["duration"]) == pytest.approx(1.0, abs=0.1)


@pytest.fixture
def musica_estereo(tmp_path):
    """Faixa de 20 s em estéreo a 44,1 kHz, como uma música baixada costuma vir."""
    arquivo = tmp_path / "musica.mp3"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=20",
         "-ac", "2", "-ar", "44100", str(arquivo)],
        check=True,
    )
    return arquivo


def _fala_de(segundos: float) -> Audio:
    tempo = np.arange(int(24_000 * segundos)) / 24_000
    return Audio.de_float(0.3 * np.sin(2 * np.pi * 440 * tempo), 24_000)


@pytest.mark.parametrize(("encerramento", "esperado"), [(Recorte(15, 5, 1, 0), 10 + 6.5 + 5), (None, 10 + 6.5)])
def test_vinheta_abre_por_baixo_da_primeira_fala_e_fecha_o_episodio(tmp_path, musica_estereo, encerramento, esperado):
    vinheta = Vinheta(musica_estereo, abertura=Recorte(5, 8, fade_saida_s=3), encerramento=encerramento, sobreposicao_s=1.5)
    destino = tmp_path / "episodio.mp3"

    exportar_mp3(_fala_de(10), destino, bitrate_kbps=64, vinheta=vinheta)

    assert duracao_mp3(destino) == pytest.approx(esperado, abs=0.15)


def test_vinheta_rejeita_sobreposicao_maior_que_o_fade():
    with pytest.raises(ValueError, match="sobreposicao_s"):
        Vinheta(Path("x.mp3"), abertura=Recorte(0, 8, fade_saida_s=2), sobreposicao_s=3)


def test_recorte_rejeita_fades_maiores_que_a_duracao():
    with pytest.raises(ValueError, match="fades"):
        Recorte(0, 3, fade_entrada_s=2, fade_saida_s=2)


def test_vinheta_lida_da_config():
    vinheta = Vinheta.de_config(Path("v.mp3"), {
        "abertura": {"inicio_s": 1, "duracao_s": 9}, "encerramento": {"inicio_s": 85, "duracao_s": 11, "fade_saida_s": 0},
        "sobreposicao_s": 2, "volume": 0.5,
    })
    assert vinheta.abertura == Recorte(1, 9)
    assert vinheta.encerramento == Recorte(85, 11, fade_saida_s=0)
    assert (vinheta.sobreposicao_s, vinheta.volume) == (2, 0.5)
