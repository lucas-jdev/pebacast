import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from podcast.audio import Audio, duracao_mp3, exportar_mp3
from podcast.dominio import Fala
from podcast.qualidade_texto import (
    GeminiTranscritor,
    IncidentesDeTexto,
    QaDeTexto,
    normalizar,
    recortar_mp3,
)
from tests.test_qualidade_audio import GhFalso

RAIZ = Path(__file__).resolve().parents[1]
precisa_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fora do PATH")

# Os cinco casos do teste do especial do Prumo (17/11), um por linha da tabela da #69.
OUVIDO_NO_PRUMO = (
    "Tô doida? Hoje a gente fala de licenças. Quem escreveu a especificação precisava entendi o especificar "
    "o domínio. E a licença do projeto é a GPL. O mercado não vem de um jeito certo de fazer isso."
)


def _falas_do_prumo(davi, helena):
    return [
        Fala(davi, "Tudo, Helena? Hoje a gente fala de licenças."),
        Fala(helena, "Quem ia escrever a especificação precisava entender e especificar o domínio."),
        Fala(davi, "E a licença do projeto é a AGPL."),
        Fala(helena, "O mercado não vende um jeito certo de fazer isso."),
    ]


class TranscritorFalso:
    def __init__(self, nome: str, texto: str) -> None:
        self.nome = nome
        self.texto = texto
        self.audios: list[bytes] = []

    def transcrever(self, audio_mp3: bytes) -> str:
        self.audios.append(audio_mp3)
        return self.texto


class TranscritorQuebrado:
    nome = "quebrado"

    def transcrever(self, audio_mp3: bytes) -> str:
        raise ConnectionError("503 UNAVAILABLE")


def _qa(primeira: str, segunda: str, incidentes=None) -> QaDeTexto:
    config = yaml.safe_load((RAIZ / "config" / "pipeline.yaml").read_text(encoding="utf-8"))["qualidade_texto"]
    textos = iter([primeira, segunda])
    qa = QaDeTexto.de_config(config, incidentes, lambda modelo: TranscritorFalso(modelo, next(textos)))
    return QaDeTexto(qa.transcritores, qa.equivalencias, qa.incidentes, recortar=lambda mp3, trecho: b"mp3")


def test_os_cinco_erros_do_prumo_ouvidos_pelos_dois_modelos_sao_confirmados(davi, helena):
    laudo = _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO).rodar("especial", Path("x.mp3"), (0, 1), _falas_do_prumo(davi, helena))

    assert not laudo.aprovado
    assert [(d.persona, d.trecho.split("[")[1].split("]")[0]) for d in laudo.divergencias] == [
        ("Davi", "tudo helena"),
        ("Helena", "ia escrever"),
        ("Helena", "entender e"),
        ("Davi", "agpl"),
        ("Helena", "vende"),
    ]
    assert dict(laudo.divergencias[3].ouvido) == {"gemini-3.6-flash": "gpl", "gemini-3.5-flash": "gpl"}
    assert laudo.divergencias[3].fala == "E a licença do projeto é a AGPL."


def test_divergencia_de_um_modelo_so_e_ruido_e_nao_conta(davi):
    fiel = "Tudo, Helena? Hoje a gente fala de licenças."
    ruidoso = "Tudo, Helena? Hoje a gente falou de licença."

    laudo = _qa(ruidoso, fiel).rodar("sw-001", Path("x"), (0, 1), [Fala(davi, fiel)])

    assert laudo.aprovado


def test_forma_de_fala_e_numero_em_algarismo_nao_sao_divergencia(davi):
    roteiro = [Fala(davi, "Pra quem está chegando agora: são vinte e cinco anos de história, tô falando sério.")]
    ouvido = "Para quem tá chegando agora, são 25 anos de história. Estou falando sério."

    laudo = _qa(ouvido, ouvido).comparar(roteiro, [ouvido, ouvido])

    assert laudo.aprovado


def test_normalizar_tira_acento_pontuacao_e_aplica_as_equivalencias():
    assert normalizar("Tá, é a AGPL!", {"ta": "esta"}) == ["esta", "e", "a", "agpl"]


def test_laudo_em_markdown_mostra_o_trecho_do_roteiro_e_o_que_cada_modelo_ouviu(davi, helena):
    laudo = _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO).comparar(_falas_do_prumo(davi, helena), [OUVIDO_NO_PRUMO] * 2)

    texto = laudo.markdown("Texto do especial")

    assert "5 divergência(s) confirmada(s)" in texto
    assert "| Davi | projeto e a [agpl] o mercado nao | gpl | gpl |" in texto


def test_divergencia_confirmada_abre_a_issue_uma_vez_e_depois_so_comenta(davi, helena):
    falas = _falas_do_prumo(davi, helena)
    gh = GhFalso()
    _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), (0, 1), falas)

    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"]
    assert criar[criar.index("--title") + 1] == "Texto do sw-004 diverge do roteiro"
    assert criar[criar.index("--label") + 1] == "incidente"
    assert "alarme falso" in criar[criar.index("--body") + 1]

    gh = GhFalso([{"number": 5, "title": "Texto do sw-004 diverge do roteiro"}])
    _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), (0, 1), falas)

    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "comment", "5"]]


def test_sem_divergencia_nao_mexe_em_issue(davi):
    gh = GhFalso()
    fiel = "Hoje a gente fala de licenças."

    _qa(fiel, fiel, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), (0, 1), [Fala(davi, fiel)])

    assert gh.comandos == []


def test_config_real_tem_dois_modelos_e_as_equivalencias_normalizadas():
    qa = _qa("", "")

    assert [transcritor.nome for transcritor in qa.transcritores] == ["gemini-3.6-flash", "gemini-3.5-flash"]
    assert qa.equivalencias["ta"] == "esta" and qa.equivalencias["pro"] == "para o"


class ErroDaApi(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"{code} erro")
        self.code = code


class ModelosFalsos:
    def __init__(self, falhas: list[Exception]) -> None:
        self.falhas = falhas
        self.chamadas = 0
        self.models = self

    def generate_content(self, model, contents):
        self.chamadas += 1
        if self.falhas:
            raise self.falhas.pop(0)
        return type("Resposta", (), {"text": "olá"})()


def test_transcritor_tenta_de_novo_quando_o_modelo_esta_indisponivel():
    pytest.importorskip("google.genai")
    esperas = []
    cliente = ModelosFalsos([ErroDaApi(503), ErroDaApi(429)])

    texto = GeminiTranscritor("modelo", cliente, espera_inicial_s=10, dormir=esperas.append).transcrever(b"mp3")

    assert texto == "olá" and esperas == [10, 20]


def test_transcritor_nao_repete_pedido_recusado():
    pytest.importorskip("google.genai")
    esperas = []
    cliente = ModelosFalsos([ErroDaApi(400)])

    with pytest.raises(ErroDaApi):
        GeminiTranscritor("modelo", cliente, dormir=esperas.append).transcrever(b"mp3")
    assert esperas == [] and cliente.chamadas == 1


@precisa_ffmpeg
def test_recorte_entrega_so_o_trecho_de_fala(tmp_path):
    tom = 0.3 * np.sin(2 * np.pi * 440 * np.arange(24_000 * 4) / 24_000)
    mp3 = tmp_path / "episodio.mp3"
    exportar_mp3(Audio.de_float(tom, 24_000), mp3, 64)
    recorte = tmp_path / "recorte.mp3"

    recorte.write_bytes(recortar_mp3(mp3, (1.0, 2.5)))

    assert duracao_mp3(recorte) == pytest.approx(1.5, abs=0.1)


def test_transcritor_quebrado_sobe_o_erro_para_a_publicacao_tratar(davi):
    qa = QaDeTexto((TranscritorQuebrado(), TranscritorQuebrado()), {}, recortar=lambda mp3, trecho: b"mp3")

    with pytest.raises(ConnectionError):
        qa.rodar("sw-001", Path("x"), (0, 1), [Fala(davi, "Oi")])
