import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from podcast.audio import Audio
from podcast.publicacao import (
    GitHubReleases,
    Resultado,
    episodios_pendentes,
    gerar_feed,
    publicar_pendentes,
    relatorio,
    resumo_da_qualidade,
    sintetizar_com_fallback,
)
from podcast.espera_de_cota import IncidentesDeCota
from podcast.qualidade_audio import IncidentesDeAudio
from podcast.qualidade_texto import QaDeTexto
from podcast.tts.provedor import CotaDiariaEsgotada, RequisicaoRecusada
from tests.conftest import ProvedorFalso, ProvedorQuebrado
from tests.test_qualidade_audio import GhFalso
from tests.test_roteiro import (  # noqa: F401 (fixture)
    CONFIG,
    _escrever_episodio,
    _gravar,
    _revisao,
    _roteiro,
    _usar_fila,
    projeto,
)

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
    [aviso] = resultado.avisos
    assert aviso.fallback and aviso.episodio_id == "sw-001" and "fallback kokoro-falso" in aviso.texto
    publicacao = json.loads((projeto.episodios / "sw-001" / "publicacao.json").read_text(encoding="utf-8"))
    assert publicacao["tts"] == {"provedor": "kokoro-falso", "fallback": True}


def test_fallback_tambem_cobre_falha_ao_criar_o_principal(davi):
    def sem_chave():
        raise KeyError("GEMINI_API_KEY")

    _, provedor, erro = sintetizar_com_fallback([], sem_chave, lambda: ProvedorFalso("kokoro"))
    assert provedor == "kokoro" and "GEMINI_API_KEY" in erro


class ProvedorSemCota:
    nome = "gemini-falso"

    def sintetizar(self, falas):
        raise CotaDiariaEsgotada("Cota diária do Gemini esgotada (gemini-falso): 429 RESOURCE_EXHAUSTED")


def _fabrica_sem_cota(criados=None):
    def fabrica(nome):
        if criados is not None:
            criados.append(nome)
        return ProvedorSemCota() if nome == "gemini-falso" else ProvedorFalso(nome)
    return fabrica


def test_cota_diaria_esgotada_nao_publica_nem_cai_no_fallback_e_aguarda(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    criados, gh = [], GhFalso()

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica_sem_cota(criados), tmp_path / "trabalho",
                                   lambda: AGORA, esperas=IncidentesDeCota("dono/repo", None, gh))

    pasta = projeto.episodios / "sw-001"
    assert resultado.publicados == [] and resultado.aguardando == ["sw-001"]
    assert criados == ["gemini-falso"]
    assert not (pasta / "publicacao.json").exists()
    assert json.loads((pasta / "aguardando_cota.json").read_text(encoding="utf-8")) == {"desde": AGORA.isoformat()}
    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"] and criar[criar.index("--label") + 1] == "incidente"
    assert criar[criar.index("--title") + 1] == "Cota do Gemini esgotada: sw-001 aguardando"
    assert relatorio(resultado)["aguardando_cota"] == ["sw-001"]


def test_cota_ainda_esgotada_comenta_na_issue_e_mantem_o_inicio_da_espera(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    pasta = projeto.episodios / "sw-001"
    (pasta / "aguardando_cota.json").write_text('{"desde": "2026-11-07T08:00:00+00:00"}\n', encoding="utf-8")
    gh = GhFalso([{"number": 7, "title": "Cota do Gemini esgotada: sw-001 aguardando"}])

    publicar_pendentes(projeto, StorageFalso(), _fabrica_sem_cota(), tmp_path / "trabalho", lambda: AGORA,
                       esperas=IncidentesDeCota("dono/repo", None, gh))

    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "comment", "7"]]
    assert "2026-11-07T08:00:00" in (pasta / "aguardando_cota.json").read_text(encoding="utf-8")


@precisa_ffmpeg
def test_episodio_que_aguardava_e_publicado_encerra_a_espera_e_fecha_a_issue(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    pasta = projeto.episodios / "sw-001"
    (pasta / "aguardando_cota.json").write_text('{"desde": "2026-11-07T08:00:00+00:00"}\n', encoding="utf-8")
    gh = GhFalso([{"number": 7, "title": "Cota do Gemini esgotada: sw-001 aguardando"}])

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA,
                                   esperas=IncidentesDeCota("dono/repo", None, gh))

    assert resultado.publicados == ["sw-001"] and resultado.aguardando == []
    assert (pasta / "publicacao.json").exists() and not (pasta / "aguardando_cota.json").exists()
    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "close", "7"]]


class EsperasQuebradas:
    def registrar(self, episodio_id, erro):
        raise subprocess.CalledProcessError(1, ["gh", "issue", "create"])

    def resolver(self, episodio_id):
        raise subprocess.CalledProcessError(1, ["gh", "issue", "close"])


def test_falha_ao_abrir_a_issue_da_cota_vira_aviso_e_o_episodio_aguarda_mesmo_assim(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica_sem_cota(), tmp_path / "trabalho",
                                   lambda: AGORA, esperas=EsperasQuebradas())

    assert resultado.aguardando == ["sw-001"]
    [aviso] = resultado.avisos
    assert not aviso.fallback and "a issue da cota esgotada não foi aberta" in aviso.texto


class ProvedorQueRecusa:
    nome = "gemini-falso"

    def sintetizar(self, falas):
        raise RequisicaoRecusada("No matching speaker voice found for name: PENDENTE")


def test_pedido_recusado_reprova_o_episodio_sem_cair_no_fallback(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    criados = []

    def fabrica(nome):
        criados.append(nome)
        return ProvedorQueRecusa() if nome == "gemini-falso" else ProvedorFalso(nome)

    resultado = _publicar(projeto, tmp_path, fabrica)

    assert resultado.publicados == []
    assert "PENDENTE" in resultado.reprovados["sw-001"][0]
    assert criados == ["gemini-falso"]
    assert not (projeto.episodios / "sw-001" / "publicacao.json").exists()


@precisa_ffmpeg
def test_feed_lista_episodios_publicados_com_enclosure_e_guid(projeto, tmp_path):
    noticia = {"tipo": "noticia", "titulo": "Apagão", "url": "https://n/1", "fonte": "Jornal", "data": "2026-11-01",
               "nota_relevancia": 8, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _publicar(projeto, tmp_path)

    canal = ET.fromstring(gerar_feed(projeto)).find("channel")
    itens = canal.findall("item")

    assert canal.find("title").text == "Pebacast"
    assert len(itens) == 1
    item = itens[0]
    assert item.find("title").text == "Saga Software · ep. 1 — Um"
    assert item.find("guid").text == "pebacast-sw-001"
    assert item.find("guid").get("isPermaLink") == "false"
    assert item.find("link").text == "https://x.github.io/pebacast/episodios/sw-001/"
    assert item.find("enclosure").get("type") == "audio/mpeg"
    assert item.find("pubDate").text == "Sun, 08 Nov 2026 01:00:00 +0000"
    notas = item.find("description").text
    assert "gerado por inteligência artificial" in notas
    assert "Vote e deixe um recado: https://x.github.io/pebacast/episodios/sw-001/" in notas
    assert "Apagão (Jornal, 2026-11-01) https://n/1" in notas
    assert "Desafio: Liste dois trade-offs." in notas


def test_titulo_no_feed_diz_a_saga_e_a_posicao_sem_mudar_o_guid(projeto):
    _usar_fila(projeto)
    for episodio, publicado_em in (("sw-002", "2026-11-09T15:00:00+00:00"), ("sl-001", "2026-11-11T15:00:00+00:00")):
        _escrever_episodio(projeto, episodio)
        _gravar(projeto.episodios / episodio / "publicacao.json", {
            "guid": f"pebacast-{episodio}", "url_audio": f"https://cdn/{episodio}.mp3", "tamanho_bytes": 1,
            "duracao_segundos": 960, "publicado_em": publicado_em,
        })

    itens = ET.fromstring(gerar_feed(projeto)).find("channel").findall("item")

    assert [(item.find("title").text, item.find("guid").text) for item in itens] == [
        ("Saga Soluções · ep. 1 — sl-001", "pebacast-sl-001"),
        ("Saga Software · ep. 2 — Dois", "pebacast-sw-002"),
    ]


def test_feed_vazio_e_valido(projeto):
    canal = ET.fromstring(gerar_feed(projeto)).find("channel")
    assert canal.findall("item") == []


def test_feed_tem_capa_dono_e_link_do_site(projeto):
    canal = ET.fromstring(gerar_feed(projeto)).find("channel")
    itunes = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"

    assert canal.find("link").text == "https://x.github.io/pebacast/"
    assert canal.find(f"{itunes}image").get("href") == "https://x.github.io/pebacast/capa-kraft.jpg"
    assert canal.find("image/url").text == "https://x.github.io/pebacast/capa-kraft.jpg"
    assert canal.find(f"{itunes}owner/{itunes}name").text == "Lucas"
    assert canal.find(f"{itunes}owner/{itunes}email").text == "lucas@exemplo.com"


def test_capa_publicada_e_quadrada_e_grande_o_bastante():
    capa = Path(__file__).parent.parent / "site" / "capa-kraft.jpg"
    dados = capa.read_bytes()
    assert dados[:3] == bytes([0xFF, 0xD8, 0xFF])  # JPEG
    assert len(dados) < 512 * 1024  # o Apple recomenda capas de até 512 KB


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
    [aviso] = resultado.avisos
    assert not aviso.fallback and "publicado sem vinheta" in aviso.texto and "VINHETA_SENHA" in aviso.texto
    assert "Vinheta de Fulano" not in gerar_feed(projeto)  # sem vinheta no áudio, sem crédito


def test_relatorio_tem_uma_entrada_por_episodio_para_as_issues():
    resultado = Resultado(
        publicados=["si-001"],
        reprovados={"sl-001": ["revisoes/3.json: a última revisão não aprovou o roteiro"], "da-001": ["sem falas"]},
        avisos=[],
    )

    dados = relatorio(resultado)

    assert dados["publicados"] == ["si-001"]
    assert set(dados["reprovados"]) == {"sl-001", "da-001"}
    assert "- revisoes/3.json" in dados["reprovados"]["sl-001"]
    assert "episodios/sl-001/revisoes/" in dados["reprovados"]["sl-001"]
    assert "sem falas" not in dados["reprovados"]["sl-001"]


def test_beta_acrescenta_o_aviso_no_fim_da_descricao_do_canal(projeto):
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "site": {"beta": True}})

    descricao = ET.fromstring(gerar_feed(projeto)).find("channel/description").text

    assert descricao.endswith("Em beta: o formato, as vozes e o visual ainda podem mudar.")


def test_sem_beta_a_descricao_do_canal_fica_como_esta(projeto):
    descricao = ET.fromstring(gerar_feed(projeto)).find("channel/description").text

    assert "beta" not in descricao.lower()


class ProvedorComPausaLonga:
    """Dois blocos com 1 s de silêncio na troca: continua fora do limite depois da montagem."""

    nome = "gemini-falso"

    def sintetizar(self, falas):
        tom = 0.3 * np.sin(2 * np.pi * 440 * np.arange(24_000) / 24_000)
        audio = Audio.de_float(np.concatenate([tom, np.zeros(24_000), tom]), 24_000)
        return Audio(audio.pcm, 24_000, trocas_s=(1.5,))


@precisa_ffmpeg
def test_audio_fora_do_padrao_e_publicado_mesmo_assim_e_abre_incidente(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    storage, gh = StorageFalso(), GhFalso()

    resultado = publicar_pendentes(projeto, storage, lambda nome: ProvedorComPausaLonga(), tmp_path / "trabalho",
                                   lambda: AGORA, IncidentesDeAudio("dono/repo", None, gh))

    assert resultado.publicados == ["sw-001"] and storage.publicados == [("sw-001", "pebacast-sw-001.mp3")]
    assert (projeto.episodios / "sw-001" / "publicacao.json").exists()
    assert not resultado.qualidade["sw-001"].aprovado
    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"] and criar[criar.index("--label") + 1] == "incidente"
    assert "Pausa na troca de blocos" in criar[criar.index("--body") + 1]


@precisa_ffmpeg
def test_episodio_que_passa_no_qa_fecha_o_incidente_aberto(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    gh = GhFalso([{"number": 9, "title": "Áudio do sw-001 fora do padrão"}])

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA,
                                   IncidentesDeAudio("dono/repo", None, gh))

    assert resultado.qualidade["sw-001"].aprovado
    assert [comando[:4] for comando in gh.acoes()] == [["gh", "issue", "close", "9"]]


class IncidentesQuebrados:
    def registrar(self, episodio_id, laudo):
        raise subprocess.CalledProcessError(1, ["gh", "issue", "create"])


@precisa_ffmpeg
def test_falha_ao_registrar_o_incidente_nao_impede_a_publicacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA,
                                   IncidentesQuebrados())

    assert resultado.publicados == ["sw-001"]
    [aviso] = resultado.avisos
    assert not aviso.fallback and "QA do áudio" in aviso.texto


class TranscritorQueRepete:
    def __init__(self, nome):
        self.nome = nome

    def transcrever(self, audio_mp3):
        assert audio_mp3, "o recorte da fala chegou vazio"
        return "palavra que não bate com o roteiro " * 200


class TranscritorIndisponivel:
    nome = "indisponivel"

    def transcrever(self, audio_mp3):
        raise ConnectionError("503 UNAVAILABLE")


@precisa_ffmpeg
def test_qa_de_texto_roda_depois_de_publicar_e_vai_para_o_resumo(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    qa = QaDeTexto((TranscritorQueRepete("a"), TranscritorQueRepete("b")), {})

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA, qa_texto=qa)

    assert resultado.publicados == ["sw-001"]
    assert not resultado.texto["sw-001"].aprovado
    assert "### Texto do sw-001" in resumo_da_qualidade(resultado)


@precisa_ffmpeg
def test_qa_de_texto_que_nao_roda_nao_segura_a_publicacao_nem_vira_aviso_de_fallback(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    qa = QaDeTexto((TranscritorIndisponivel(), TranscritorIndisponivel()), {})

    resultado = publicar_pendentes(projeto, StorageFalso(), _fabrica(), tmp_path / "trabalho", lambda: AGORA, qa_texto=qa)

    assert resultado.publicados == ["sw-001"]
    assert resultado.texto_nao_rodou["sw-001"].startswith("QA de texto não rodou")
    assert resultado.avisos == []
    assert "QA de texto não rodou" in resumo_da_qualidade(resultado)
