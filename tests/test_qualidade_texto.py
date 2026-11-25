import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from podcast.audio import Audio, Trechos, duracao_mp3, exportar_mp3
from podcast.dominio import Fala
from podcast.qualidade_texto import (
    GeminiTranscritor,
    IncidentesDeTexto,
    QaDeTexto,
    TranscricaoIncompleta,
    janelas,
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
    laudo = _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO).rodar("especial", Path("x.mp3"), Trechos(fala=(0, 1)), _falas_do_prumo(davi, helena))

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

    laudo = _qa(ruidoso, fiel).rodar("sw-001", Path("x"), Trechos(fala=(0, 1)), [Fala(davi, fiel)])

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
    _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), Trechos(fala=(0, 1)), falas)

    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"]
    assert criar[criar.index("--title") + 1] == "Texto do sw-004 diverge do roteiro"
    assert criar[criar.index("--label") + 1] == "incidente"
    assert "alarme falso" in criar[criar.index("--body") + 1]

    gh = GhFalso([{"number": 5, "title": "Texto do sw-004 diverge do roteiro"}])
    _qa(OUVIDO_NO_PRUMO, OUVIDO_NO_PRUMO, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), Trechos(fala=(0, 1)), falas)

    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "comment", "5"]]


def test_sem_divergencia_nao_mexe_em_issue(davi):
    gh = GhFalso()
    fiel = "Hoje a gente fala de licenças."

    _qa(fiel, fiel, IncidentesDeTexto("dono/repo", None, gh)).rodar("sw-004", Path("x"), Trechos(fala=(0, 1)), [Fala(davi, fiel)])

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
        qa.rodar("sw-001", Path("x"), Trechos(fala=(0, 1)), [Fala(davi, "Oi")])


def test_janelas_cortam_na_troca_de_bloco_mais_tardia_que_cabe():
    assert janelas((10.0, 990.0), (250.0, 300.0, 560.0, 800.0), 300.0) == [
        (10.0, 300.0), (300.0, 560.0), (560.0, 800.0), (800.0, 990.0)]


def test_janela_sem_troca_por_perto_corta_no_maximo():
    assert janelas((0.0, 700.0), (), 300.0) == [(0.0, 300.0), (300.0, 600.0), (600.0, 700.0)]


def test_cada_modelo_transcreve_janela_por_janela_e_as_partes_sao_juntadas(davi):
    partes = iter(["Hoje a gente", "fala de licenças.", "Hoje a gente", "fala de licenças."])

    class Transcritor:
        def __init__(self, nome):
            self.nome, self.audios = nome, []

        def transcrever(self, audio):
            self.audios.append(audio)
            return next(partes)

    a, b = Transcritor("a"), Transcritor("b")
    recortes = []
    qa = QaDeTexto((a, b), {}, recortar=lambda mp3, trecho: recortes.append(trecho) or repr(trecho).encode(),
                   janela_maxima_s=300)

    laudo = qa.rodar("sw-001", Path("x"), Trechos(fala=(0.0, 500.0), trocas_s=(240.0,)),
                     [Fala(davi, "Hoje a gente fala de licenças.")])

    assert recortes == [(0.0, 240.0), (240.0, 500.0)]
    assert len(a.audios) == len(b.audios) == 2
    assert laudo.aprovado


def test_transcricao_cortada_no_meio_nao_vira_divergencia_e_sim_erro(davi, helena):
    # No se-002, os dois modelos pararam em 69% do roteiro, e o resto do episódio virou "divergência".
    falas = _falas_do_prumo(davi, helena)
    cortada = "Tudo, Helena? Hoje a gente fala de licenças. Quem ia escrever a especificação"
    gh = GhFalso()

    with pytest.raises(TranscricaoIncompleta, match="mínimo 85%"):
        _qa(cortada, cortada, IncidentesDeTexto("dono/repo", None, gh)).rodar("se-002", Path("x"), Trechos(fala=(0, 1)), falas)
    assert gh.comandos == []


def test_trechos_do_mesmo_ponto_do_roteiro_viram_uma_linha_so_e_trecho_longo_e_resumido(davi):
    roteiro = "um dois tres quatro cinco seis sete oito nove dez onze doze treze quatorze quinze dezesseis fim"
    # O modelo a ouve palavras soltas no lugar; o b não ouve nada: todas caem no mesmo trecho do b.
    ouvido_a = "um x tres x cinco x sete x nove x onze x treze x quinze x fim"
    ouvido_b = "um fim"
    qa = QaDeTexto((TranscritorFalso("a", ""), TranscritorFalso("b", "")), {}, cobertura_minima=0)

    laudo = qa.comparar([Fala(davi, roteiro)], [ouvido_a, ouvido_b])

    [divergencia] = laudo.divergencias
    assert "… (+3 palavras)" in divergencia.trecho
    assert divergencia.ouvido["b"] == ""


class RespostaCortada:
    text = "Tudo, Helena? Hoje a gente"
    candidates = [type("Candidato", (), {"finish_reason": "FinishReason.MAX_TOKENS"})()]


def test_resposta_parada_no_limite_de_tokens_nao_e_repetida():
    pytest.importorskip("google.genai")
    esperas = []

    class Modelos:
        chamadas = 0

        def generate_content(self, model, contents):
            Modelos.chamadas += 1
            return RespostaCortada()

    cliente = type("Cliente", (), {"models": Modelos()})()

    with pytest.raises(TranscricaoIncompleta, match="limite de tokens"):
        GeminiTranscritor("modelo", cliente, dormir=esperas.append).transcrever(b"mp3")
    assert Modelos.chamadas == 1 and esperas == []


# Ruído da transcrição (#132): casos reais dos incidentes do sw-004, se-002 e co-002.

@pytest.mark.parametrize(("roteiro", "ouvido"), [
    ("dados e marcou fronteira de confiança", "dados e marcou a fronteira de confiança"),  # se-002
    ("e de spoofing e se passar por", "e de spoofing se passar por"),  # se-002
    ("o mesmo arquivo pras duas funções", "o mesmo arquivo para as duas funções"),  # sw-004
    ("corpo da mensagem perai isso é exatamente", "corpo da mensagem pera aí isso é exatamente"),  # sw-004
    ("pequeno e arquitetural num sistema em que", "pequeno e arquitetural no sistema em que"),  # sw-004
    ("e quais são os trade-offs aqui, porque nada é de graça", "e quais são os tradeoffs aqui, porque nada é de graça"),
])
def test_artigo_solto_contracao_e_separacao_sao_ruido_da_transcricao(davi, roteiro, ouvido):
    laudo = _qa(ouvido, ouvido).comparar([Fala(davi, roteiro)], [ouvido, ouvido])

    assert laudo.aprovado, laudo.markdown("ruído")


@pytest.mark.parametrize(("roteiro", "ouvido", "trecho"), [
    ("um repositório da NVIDIA chamado Nodewright que é", "um repositório da NVIDIA chamado Nygard que é", "nodewright"),
    ("e por isso não muda a decisão que o time tomou", "e por isso muda a decisão que o time tomou", "nao"),
    ("aceito o risco nem que seja por escrito", "aceito o risco que seja por escrito", "nem"),
])
def test_palavra_de_conteudo_e_negacao_continuam_no_laudo(davi, roteiro, ouvido, trecho):
    # O "Nygard" no lugar de "Nodewright" foi o acerto de verdade do sw-004, perdido no meio do ruído.
    laudo = _qa(ouvido, ouvido).comparar([Fala(davi, roteiro)], [ouvido, ouvido])

    [divergencia] = laudo.divergencias
    assert f"[{trecho}]" in divergencia.trecho
