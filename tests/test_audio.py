import json
import subprocess

import numpy as np
import pytest

from podcast.audio import Audio, concatenar, exportar_mp3


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
