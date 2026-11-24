import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from podcast.audio import Trechos
from podcast.dominio import Fala
from podcast.pronuncia import Pronuncia
from podcast.publicacao import publicar_pendentes, resumo_da_qualidade
from podcast.qualidade_pronuncia import (
    ESQUEMA,
    GeminiOuvinte,
    IncidentesDePronuncia,
    LaudoDePronuncia,
    Ocorrencia,
    QaDePronuncia,
    RespostaInvalida,
    ler_resposta,
    main,
    termos_do_roteiro,
)
from podcast.qualidade_texto import TranscricaoIncompleta
from podcast.regravacao import regravar
from tests.test_publicacao import AGORA, StorageFalso, _fabrica
from tests.test_qualidade_audio import GhFalso
from tests.test_regravacao import ReleasesFalso, _ja_publicado
from tests.test_roteiro import _escrever_episodio, projeto  # noqa: F401 (fixture)

precisa_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fora do PATH")
PEBACAST = Pronuncia("Pebacast", instrucao="E aberto: PÉ-ba-cast.")
TRECHOS = Trechos(fala=(10.0, 590.0), trocas_s=(300.0,))


class OuvinteFixo:
    """Devolve as mesmas ocorrências em toda janela e guarda o que recebeu."""

    def __init__(self, nome: str, *ocorrencias: Ocorrencia) -> None:
        self.nome = nome
        self._ocorrencias = list(ocorrencias)
        self.pedidos: list[tuple[bytes, list[str]]] = []

    def ouvir(self, audio_mp3, termos):
        assert audio_mp3, "o recorte da fala chegou vazio"
        self.pedidos.append((audio_mp3, [termo.termo for termo in termos]))
        return list(self._ocorrencias)


class OuvinteIndisponivel:
    nome = "indisponivel"

    def ouvir(self, audio_mp3, termos):
        raise ConnectionError("503 UNAVAILABLE")


def errado(segundo=12.0, ouvido="pêbacast"):
    return Ocorrencia("Pebacast", segundo, "errado", ouvido)


def certo(segundo=40.0):
    return Ocorrencia("Pebacast", segundo, "certo", "pébacast")


def qa(*ouvintes, incidentes=None, pronuncias=(PEBACAST,)):
    return QaDePronuncia(tuple(ouvintes), tuple(pronuncias), incidentes, recortar=lambda mp3, trecho: b"mp3")


@pytest.fixture
def falas(davi, helena):
    return [Fala(davi, "Bem-vindos ao Pebacast!"), Fala(helena, "Oi."), Fala(davi, "Este foi o pebacast.")]


def test_confere_so_termos_com_instrucao_que_o_roteiro_cita(falas):
    pronuncias = [PEBACAST, Pronuncia("Boehm", escrever_como="Bím"), Pronuncia("Kubernetes", instrucao="kubernêtis")]

    termos = termos_do_roteiro(falas, pronuncias)

    assert list(termos) == ["Pebacast"]
    assert termos["Pebacast"] == (PEBACAST, 2)


def test_procura_o_termo_no_texto_original_e_nao_na_grafia_trocada(davi):
    trocada = Pronuncia("Pebacast", escrever_como="Péba-cast", instrucao="E aberto.")

    assert termos_do_roteiro([Fala(davi, "Bem-vindos ao Pebacast!")], [trocada])
    assert not termos_do_roteiro([Fala(davi, "Bem-vindos ao Péba-cast!")], [trocada])


def test_roteiro_sem_termo_do_dicionario_nao_faz_nenhuma_requisicao(davi, tmp_path):
    a, b = OuvinteFixo("a"), OuvinteFixo("b")

    laudo = qa(a, b).rodar("sw-001", tmp_path / "x.mp3", TRECHOS, [Fala(davi, "Oi, gente.")])

    assert laudo is None
    assert a.pedidos == b.pedidos == []


def test_erro_de_um_modelo_so_nao_e_confirmado(falas, tmp_path):
    laudo = qa(OuvinteFixo("a", errado()), OuvinteFixo("b", certo())).rodar("sw-001", tmp_path / "x.mp3", TRECHOS, falas)

    assert laudo.aprovado
    assert "Nenhum erro de pronúncia confirmado" in laudo.markdown("Pronúncia do sw-001")


def test_erro_dos_dois_modelos_na_mesma_janela_e_confirmado_com_o_instante_no_mp3(falas, tmp_path):
    a, b = OuvinteFixo("a", errado(12.0, "pêbacast")), OuvinteFixo("b", errado(13.0, "pebacást"))

    laudo = qa(a, b).rodar("sw-001", tmp_path / "x.mp3", TRECHOS, falas)

    assert len(a.pedidos) == 2, "uma requisição por janela, cortada na troca de bloco"
    assert [erro.instante_s for erro in laudo.erros] == [22.0, 312.0]
    assert laudo.erros[0].ouvido == {"a": "pêbacast", "b": "pebacást"}
    assert "| Pebacast | 00:22 | pêbacast | pebacást |" in laudo.markdown("Pronúncia do sw-001")


def test_laudo_aprovado_mostra_quantas_vezes_cada_modelo_ouviu_o_termo(falas, tmp_path):
    laudo = qa(OuvinteFixo("a", certo()), OuvinteFixo("b")).rodar("sw-001", tmp_path / "x.mp3", TRECHOS, falas)

    relatorio = laudo.markdown("Pronúncia do sw-001")

    assert "| Termo | No roteiro | a | b |" in relatorio
    assert "| Pebacast | 2 | 2 / 0 | 0 / 0 |" in relatorio


def test_resposta_valida_vira_ocorrencias():
    texto = json.dumps({"ocorrencias": [{"termo": "Pebacast", "segundo": 3, "veredito": "errado", "ouvido": "pêba"}]})

    assert ler_resposta(texto, [PEBACAST]) == [Ocorrencia("Pebacast", 3.0, "errado", "pêba")]


@pytest.mark.parametrize("texto", [
    "não é json",
    json.dumps({"outra": []}),
    json.dumps({"ocorrencias": [{"termo": "Pebacast", "segundo": 1}]}),
    json.dumps({"ocorrencias": [{"termo": "Kubernetes", "segundo": 1, "veredito": "certo", "ouvido": "x"}]}),
    json.dumps({"ocorrencias": [{"termo": "Pebacast", "segundo": 1, "veredito": "talvez", "ouvido": "x"}]}),
])
def test_resposta_fora_do_esquema_ou_do_pedido_e_invalida(texto):
    with pytest.raises(RespostaInvalida):
        ler_resposta(texto, [PEBACAST])


class ClienteFalso:
    def __init__(self, texto="", motivo="STOP"):
        self.chamadas = []
        self._resposta = SimpleNamespace(text=texto, candidates=[SimpleNamespace(finish_reason=motivo)])
        self.models = self

    def generate_content(self, **pedido):
        self.chamadas.append(pedido)
        return self._resposta


def test_gemini_pede_json_no_esquema_com_a_instrucao_de_cada_termo():
    pytest.importorskip("google.genai")
    cliente = ClienteFalso(json.dumps({"ocorrencias": []}))

    assert GeminiOuvinte("modelo", cliente=cliente).ouvir(b"mp3", [PEBACAST]) == []

    [pedido] = cliente.chamadas
    assert pedido["config"].response_mime_type == "application/json"
    assert pedido["config"].response_json_schema == ESQUEMA
    assert "E aberto: PÉ-ba-cast." in pedido["contents"][1]


def test_gemini_cortado_no_limite_de_tokens_nao_tenta_de_novo():
    pytest.importorskip("google.genai")
    cliente = ClienteFalso('{"ocorrencias": [', motivo="FinishReason.MAX_TOKENS")

    with pytest.raises(TranscricaoIncompleta):
        GeminiOuvinte("modelo", cliente=cliente, dormir=lambda _: None).ouvir(b"mp3", [PEBACAST])
    assert len(cliente.chamadas) == 1


def test_erro_confirmado_abre_issue_incidente_e_aprovado_nao():
    gh = GhFalso()
    incidentes = IncidentesDePronuncia("dono/repo", "https://run/1", gh)
    reprovado = LaudoDePronuncia(("a", "b"), (), (SimpleNamespace(termo="Pebacast", instante_s=5.0, ouvido={"a": "x", "b": "y"}),))

    incidentes.registrar("sw-001", LaudoDePronuncia(("a", "b"), (), ()))
    assert gh.acoes() == []

    incidentes.registrar("sw-001", reprovado)
    [criacao] = gh.acoes()
    assert criacao[:3] == ["gh", "issue", "create"]
    assert "Pronúncia do sw-001 diverge do dicionário" in criacao


def test_config_le_o_dicionario_do_tts_e_a_janela():
    criados = []
    config_tts = {"pronuncia": [{"termo": "Pebacast", "instrucao": "E aberto."}]}

    qa_ = QaDePronuncia.de_config({"modelos": ["m1", "m2"], "janela_maxima_s": 120}, config_tts,
                                  criar_ouvinte=lambda modelo: criados.append(modelo) or OuvinteFixo(modelo))

    assert criados == ["m1", "m2"]
    assert qa_.pronuncias == (Pronuncia("Pebacast", instrucao="E aberto."),)
    assert qa_.janela_maxima_s == 120


def test_cli_avisa_quando_o_roteiro_nao_cita_termo_do_dicionario(tmp_path, capsys):
    config = tmp_path / "pipeline.yaml"
    config.write_text("tts:\n  pronuncia: []\nqualidade_pronuncia:\n  modelos: [m1, m2]\n", encoding="utf-8")
    roteiro = tmp_path / "roteiro.json"
    roteiro.write_text(json.dumps({"falas": [{"persona": "davi", "texto": "Oi."}]}), encoding="utf-8")

    assert main([str(tmp_path / "x.mp3"), str(roteiro), "--config", str(config)]) == 0
    assert "não cita nenhum termo" in capsys.readouterr().out


@precisa_ffmpeg
def test_qa_de_pronuncia_roda_depois_de_publicar_e_vai_para_o_resumo(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    qa_ = QaDePronuncia((OuvinteFixo("a", errado()), OuvinteFixo("b", errado())), (PEBACAST,))

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA,
                                   qa_pronuncia=qa_)

    assert resultado.publicados == ["sw-001"]
    assert not resultado.pronuncia["sw-001"].aprovado
    assert "### Pronúncia do sw-001" in resumo_da_qualidade(resultado)


@precisa_ffmpeg
def test_qa_de_pronuncia_que_nao_roda_nao_segura_a_publicacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    qa_ = QaDePronuncia((OuvinteIndisponivel(), OuvinteIndisponivel()), (PEBACAST,))

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA,
                                   qa_pronuncia=qa_)

    assert resultado.publicados == ["sw-001"]
    assert resultado.pronuncia_nao_rodou["sw-001"].startswith("QA de pronúncia não rodou")
    assert resultado.avisos == []
    assert "QA de pronúncia não rodou" in resumo_da_qualidade(resultado)


@precisa_ffmpeg
def test_regravar_mostra_o_laudo_de_pronuncia_da_candidata(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    qa_ = qa(OuvinteFixo("a", errado()), OuvinteFixo("b", errado()))

    candidata = regravar(projeto, "sw-001", releases, lambda nome: _fabrica()(nome), tmp_path / "trabalho", qa_)

    assert not candidata.pronuncia.aprovado
    relatorio = candidata.markdown("sw-001")
    assert relatorio.index("### Qualidade da candidata") < relatorio.index("### Pronúncia da candidata do sw-001")


@precisa_ffmpeg
def test_regravar_com_qa_de_pronuncia_quebrado_mantem_a_candidata(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)

    candidata = regravar(projeto, "sw-001", releases, lambda nome: _fabrica()(nome), tmp_path / "trabalho",
                         qa(OuvinteIndisponivel(), OuvinteIndisponivel()))

    assert "pebacast-sw-001-candidata.mp3" in releases.assets["sw-001"]
    assert candidata.pronuncia is None
    assert "QA de pronúncia não rodou" in candidata.markdown("sw-001")
