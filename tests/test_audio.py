import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from podcast.audio import (
    Audio,
    Recorte,
    Trechos,
    Vinheta,
    aparar_bordas,
    concatenar,
    duracao_mp3,
    exportar_mp3,
    medir_loudness,
)


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
        "sobreposicao_s": 2, "abaixo_da_fala_lu": 3,
    })
    assert vinheta.abertura == Recorte(1, 9)
    assert vinheta.encerramento == Recorte(85, 11, fade_saida_s=0)
    assert (vinheta.sobreposicao_s, vinheta.abaixo_da_fala_lu) == (2, 3)


def test_vinheta_rejeita_musica_acima_da_fala():
    with pytest.raises(ValueError, match="abaixo_da_fala_lu"):
        Vinheta(Path("x.mp3"), abertura=Recorte(0, 8), abaixo_da_fala_lu=-1)


def _com_bordas(segundos_de_fala: float, silencio_ms: int) -> Audio:
    borda = np.zeros(24_000 * silencio_ms // 1000)
    tempo = np.arange(int(24_000 * segundos_de_fala)) / 24_000
    return Audio.de_float(np.concatenate([borda, 0.3 * np.sin(2 * np.pi * 440 * tempo), borda]), 24_000)


def test_aparar_bordas_tira_o_silencio_e_deixa_so_a_folga():
    aparado = aparar_bordas(_com_bordas(1.0, silencio_ms=500), folga_ms=30)

    assert aparado.duracao_segundos == pytest.approx(1.0 + 2 * 0.03, abs=0.002)


def test_aparar_bordas_devolve_parte_toda_em_silencio_como_esta():
    silencio = Audio.silencio(200, 24_000)

    assert aparar_bordas(silencio) == silencio


def test_concatenar_marca_as_trocas_no_meio_de_cada_pausa():
    parte = Audio.silencio(1000, 24_000)

    resultado = concatenar([parte, parte, parte], pausa_ms=300)

    assert resultado.trocas_s == pytest.approx((1.15, 2.45))


def test_concatenar_aparando_deixa_entre_os_blocos_so_a_pausa_fixa():
    blocos = [_com_bordas(1.0, silencio_ms=450), _com_bordas(1.0, silencio_ms=450)]

    resultado = concatenar(blocos, pausa_ms=300, aparar=True)

    folga = 0.03
    assert resultado.duracao_segundos == pytest.approx(2 * (1.0 + 2 * folga) + 0.3, abs=0.002)
    assert resultado.trocas_s == pytest.approx((1.0 + 2 * folga + 0.15,), abs=0.002)


def _medir(mp3: Path, trecho: tuple[float, float] | None = None):
    corte = ["-ss", str(trecho[0]), "-to", str(trecho[1])] if trecho else []
    return medir_loudness([*corte, "-i", str(mp3)], "[0:a]anull[medir]")


def test_exportar_mp3_limita_o_pico_real_e_acerta_a_loudness(tmp_path):
    rng = np.random.default_rng(7)
    tempo = np.arange(24_000 * 10) / 24_000
    # Fala baixa com estalos perto do 0 dBFS: o loudnorm deixava esse tipo de pico passar do alvo.
    fala = 0.1 * np.sin(2 * np.pi * 300 * tempo) + (rng.random(tempo.size) < 0.0005) * 0.98
    destino = tmp_path / "picos.mp3"

    exportar_mp3(Audio.de_float(fala, 24_000), destino, bitrate_kbps=64)

    medida = _medir(destino)
    assert medida.pico_real_dbtp <= -1.5 + 0.2
    assert medida.integrada_lufs == pytest.approx(-16, abs=0.5)



def test_montagem_insiste_no_teto_enquanto_o_codificador_empurra_o_pico(tmp_path, monkeypatch):
    # O se-002 (21/11) saiu com -0,7 dBTP: corrigir a loudness empurrava o pico de volta, e o
    # codificador sobe mais o pico quanto mais baixo o teto. Três passadas não bastavam.
    import podcast.audio as modulo

    passadas = []

    def codificar(entradas, grafo, taxa, ganho_db, teto_dbtp, destino, *resto):
        passadas.append((ganho_db, teto_dbtp))

    def mp3_simulado(ganho_db, teto_dbtp):
        pico = teto_dbtp + 1.5 * (ganho_db - 0.2) + 0.6 * (-1.5 - teto_dbtp)
        return modulo.Loudness(-16.4 + (ganho_db - 0.2), pico)

    def medir(entradas, grafo):
        return mp3_simulado(*passadas[-1]) if passadas else modulo.Loudness(-16.2, -3.0)

    monkeypatch.setattr(modulo, "_codificar", codificar)
    monkeypatch.setattr(modulo, "medir_loudness", medir)

    exportar_mp3(Audio.de_float(np.zeros(24_000), 24_000), tmp_path / "e.mp3", bitrate_kbps=64)

    final = mp3_simulado(*passadas[-1])
    assert len(passadas) > 3
    assert final.pico_real_dbtp <= modulo.ALVO_PICO_DBTP
    assert final.integrada_lufs == pytest.approx(-16, abs=0.2)

def test_exportar_mp3_sem_vinheta_devolve_a_fala_e_as_trocas(tmp_path):
    fala = concatenar([_fala_de(1), _fala_de(1)], pausa_ms=300)

    trechos = exportar_mp3(fala, tmp_path / "e.mp3", bitrate_kbps=64)

    assert trechos == Trechos(fala=(0.0, pytest.approx(2.3)), trocas_s=(pytest.approx(1.15),))


def test_vinheta_fica_abaixo_da_fala_mesmo_com_a_faixa_alta(tmp_path):
    musica = tmp_path / "alta.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=20:a=0.9",
                    str(musica)], check=True)
    vinheta = Vinheta(musica, abertura=Recorte(0, 6, fade_entrada_s=0, fade_saida_s=2),
                      encerramento=Recorte(10, 6, fade_entrada_s=0, fade_saida_s=0), sobreposicao_s=1,
                      abaixo_da_fala_lu=2)
    fala = Audio.de_float(0.05 * np.sin(2 * np.pi * 440 * np.arange(24_000 * 10) / 24_000), 24_000)
    destino = tmp_path / "episodio.mp3"

    trechos = exportar_mp3(fala, destino, bitrate_kbps=64, vinheta=vinheta)

    assert trechos.abertura == (0.0, 5.0) and trechos.fala == (5.0, 15.0) and trechos.encerramento == (15.0, 21.0)
    fala_lufs = _medir(destino, trechos.fala).integrada_lufs
    assert _medir(destino, trechos.abertura).integrada_lufs <= fala_lufs
    assert _medir(destino, trechos.encerramento).integrada_lufs <= fala_lufs


def test_musica_fica_abaixo_da_fala_no_mp3_mesmo_quando_o_limitador_baixa_a_fala(tmp_path):
    # #142: a fala do TTS tem picos que o limitador corta, e a música quase não. Com o ganho do
    # episódio aplicado depois da mistura, compensar a fala subia a música junto: no si-003, a
    # abertura saiu 0,9 LU acima da fala. Aqui, sílabas baixas com estalos perto do 0 dBFS fazem
    # a música sair uns 4 LU acima da fala nessa montagem.
    musica = tmp_path / "rosa.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anoisesrc=d=30:a=0.3:c=pink", str(musica)], check=True)
    tempo = np.arange(24_000 * 20) / 24_000
    silabas = 0.05 * np.sin(2 * np.pi * 200 * tempo) * (np.sin(2 * np.pi * 4 * tempo) > 0)
    estalos = (np.arange(tempo.size) % 2400 == 0) * 0.98
    vinheta = Vinheta(musica, abertura=Recorte(0, 6, fade_entrada_s=0, fade_saida_s=2),
                      encerramento=Recorte(10, 6, fade_entrada_s=0, fade_saida_s=0), sobreposicao_s=1,
                      abaixo_da_fala_lu=2)
    destino = tmp_path / "episodio.mp3"

    trechos = exportar_mp3(Audio.de_float(silabas + estalos, 24_000), destino, bitrate_kbps=64, vinheta=vinheta)

    # Medido como o qualidade_audio.py mede: cada trecho do MP3 publicado.
    fala = _medir(destino, trechos.fala).integrada_lufs
    assert _medir(destino, trechos.abertura).integrada_lufs - fala <= -2
    assert _medir(destino, trechos.encerramento).integrada_lufs - fala <= -2
    episodio = _medir(destino)
    assert episodio.integrada_lufs == pytest.approx(-16, abs=1)
    assert episodio.pico_real_dbtp <= -1


def test_correcao_da_musica_mira_a_faixa_abaixo_do_alvo(tmp_path, monkeypatch):
    import podcast.audio as modulo

    medidas = {(0.0, 5.0): -15.0, (5.0, 15.0): -16.0, (15.0, 21.0): -18.2}
    monkeypatch.setattr(modulo, "medir_trecho", lambda mp3, trecho=None: modulo.Loudness(medidas[trecho], -2))
    vinheta = Vinheta(Path("v.mp3"), abertura=Recorte(0, 6, fade_saida_s=2), sobreposicao_s=1, abaixo_da_fala_lu=2)

    correcoes = modulo.correcao_da_musica(Path("e.mp3"), Trechos((5.0, 15.0), (), (0.0, 5.0), (15.0, 21.0)), vinheta)

    # A abertura está 1 LU acima da fala e desce para o meio da faixa aceita (-2,25 LU). O
    # encerramento, a -2,2 LU, já está na faixa e fica como está.
    assert correcoes == pytest.approx((-3.25, 0.0))
