import json
from pathlib import Path

import numpy as np
import pytest

from podcast import qualidade_voz as qv
from podcast.audio import Trechos
from podcast.dominio import Fala, Persona, Voz
from podcast.publicacao import publicar_pendentes, relatorio
from podcast.qualidade_voz import (
    IncidentesDeVoz,
    LaudoDeVoz,
    LimitesDeVoz,
    Medidas,
    Modelo,
    ModeloIndisponivel,
    QaDeVoz,
    Referencia,
    a_regravar,
    avaliar,
    disparar_regravacao,
    obter_modelo,
    referencia_de,
)
from podcast.regravacao import COMENTARIO_DE_COTA, RegravacaoInvalida, regravar, substituir
from podcast.tts.provedor import CotaDiariaEsgotada
from tests.conftest import ProvedorFalso, ProvedorQuebrado
from tests.test_qualidade_audio import GhFalso
from tests.test_regravacao import ReleasesFalso, _fabrica, _ja_publicado, precisa_ffmpeg
from tests.test_roteiro import _escrever_episodio, projeto  # noqa: F401 (fixture)

SHA = "a" * 64
DIM = 256
RNG = np.random.default_rng(21)
PERSONAS = {
    "davi": Persona("davi", "Davi", Voz("Puck", "pm_alex", "x", "")),
    "helena": Persona("helena", "Helena", Voz("Kore", "pf_dora", "x", "")),
}


def _voz() -> np.ndarray:
    vetor = RNG.normal(size=DIM)
    return vetor / np.linalg.norm(vetor)


DAVI, HELENA, OUTRA = _voz(), _voz(), _voz()


def _miolos(base: np.ndarray, quantos: int, ruido: float = 0.25) -> np.ndarray:
    vetores = base + ruido * RNG.normal(size=(quantos, DIM)) / np.sqrt(DIM)
    return vetores / np.linalg.norm(vetores, axis=1, keepdims=True)


def _episodio(davi=DAVI, helena=HELENA, helena_no_bloco_1=None, blocos=3, por_bloco=4) -> Medidas:
    """Medidas de um episódio com o Davi e a Helena em `blocos` blocos, `por_bloco` miolos de cada um."""
    persona, bloco, vetores = [], [], []
    for numero in range(blocos):
        for pid, voz in (("davi", davi), ("helena", helena_no_bloco_1 if numero == 1 and helena_no_bloco_1 is not None
                                           else helena)):
            persona += [pid] * por_bloco
            bloco += [numero] * por_bloco
            vetores.append(_miolos(voz, por_bloco))
    f0 = np.array([136.0 if p == "davi" else 194.0 for p in persona])
    return Medidas(np.array(persona, dtype=object), np.array(bloco), np.concatenate(vetores).astype(np.float32), f0)


def _referencia(sha=SHA, davi=DAVI, helena=HELENA, voz_helena="Kore") -> Referencia:
    return Referencia(sha, {
        "davi": qv.ImpressaoDeVoz("Puck", tuple(davi), ("sw-001",), "2026-11-27"),
        "helena": qv.ImpressaoDeVoz(voz_helena, tuple(helena), ("sw-001",), "2026-11-27"),
    })


def _qa(referencia=None, **opcoes) -> QaDeVoz:
    return QaDeVoz(Modelo("https://modelo", SHA), PERSONAS, 4000, referencia or _referencia(), **opcoes)


# Regras


def test_episodio_bom_passa_em_todas_as_medidas():
    laudo = _qa().avaliar(_episodio())

    assert laudo.aprovado, laudo.problemas
    assert {p.persona: p.contra_a_referencia > 0.92 for p in laudo.personas} == {"davi": True, "helena": True}
    assert all(b.contra_o_episodio > 0.75 for b in laudo.blocos)


def test_timbre_trocado_num_bloco_reprova_pelo_bloco():
    laudo = _qa().avaliar(_episodio(helena_no_bloco_1=OUTRA))

    assert not laudo.aprovado
    assert any("Helena muda de timbre no bloco 2" in problema for problema in laudo.problemas)


def test_convidada_com_a_voz_do_davi_reprova_por_vozes_confundiveis():
    laudo = _qa(Referencia("", {})).avaliar(_episodio(helena=DAVI))

    [problema] = laudo.problemas
    assert "Davi e Helena soam como a mesma voz" in problema and "136 Hz" in problema and "194 Hz" in problema


def test_convidada_inteira_com_outra_voz_so_a_referencia_pega():
    # Por dentro, o episódio é coerente: só a impressão de voz de referência mostra que a Helena não é ela.
    sem_referencia = _qa(Referencia("", {})).avaliar(_episodio(helena=OUTRA))
    com_referencia = _qa().avaliar(_episodio(helena=OUTRA))

    assert sem_referencia.aprovado
    assert not com_referencia.aprovado
    assert any("Helena no episódio inteiro não soa como a própria referência" in p for p in com_referencia.problemas)


def test_bloco_com_poucos_trechos_nao_e_julgado_e_o_laudo_diz():
    medidas = _episodio(por_bloco=1)

    laudo = _qa().avaliar(medidas)

    assert all(bloco.contra_o_episodio is None for bloco in laudo.blocos)
    assert "não julgado: menos de 2 trechos" in laudo.markdown("Voz do sw-001")


# Referência


@pytest.mark.parametrize(("referencia", "motivo"), [
    (Referencia("", {}), "sem referência (estreia"),
    (_referencia(sha="b" * 64), "medida com outro modelo"),
    (_referencia(voz_helena="Erinome"), "a voz do Gemini mudou (Erinome → Kore)"),
])
def test_sem_referencia_valida_so_as_medidas_internas_rodam_e_o_laudo_diz_por_que(referencia, motivo):
    # A Helena com outra voz inteira passaria pela referência; sem ela, só as medidas de dentro contam.
    laudo = _qa(referencia).avaliar(_episodio(helena=OUTRA))

    helena = next(p for p in laudo.personas if p.persona == "helena")
    assert helena.contra_a_referencia is None and motivo in helena.sem_referencia
    assert motivo in laudo.markdown("Voz do sw-001")
    assert laudo.aprovado
    assert all(b.contra_a_referencia is None for b in laudo.blocos if b.persona == "helena")


def test_referencia_e_a_media_dos_centroides_e_volta_igual_do_arquivo(tmp_path):
    referencia = referencia_de({"sw-001": _episodio(), "sw-002": _episodio()}, PERSONAS, SHA, hoje="2026-11-27")
    arquivo = tmp_path / "vozes-referencia.json"

    referencia.gravar(arquivo)
    lida = Referencia.ler(arquivo)

    assert lida.modelo_sha256 == SHA
    assert lida.personas["helena"].voz == "Kore" and lida.personas["helena"].episodios == ("sw-001", "sw-002")
    assert float(np.array(lida.personas["davi"].vetor) @ DAVI) > 0.95
    assert len(lida.personas["davi"].vetor) == DIM


def test_comando_referencia_mede_so_os_episodios_indicados(tmp_path, monkeypatch):
    medidos = []
    monkeypatch.setattr(qv, "_qa", lambda raiz: _qa())
    monkeypatch.setattr(qv, "baixar_publicado", lambda repo, ep, pasta: (pasta / f"{ep}.mp3").touch() or pasta / f"{ep}.mp3")
    monkeypatch.setattr(qv, "medir_publicado", lambda qa, raiz, ep, mp3: medidos.append(ep) or _episodio())
    saida = tmp_path / "vozes-referencia.json"

    assert qv.main(["--raiz", str(tmp_path), "referencia", "--repo", "d/r", "--episodios", "sw-001", "in-001",
                    "--saida", str(saida)]) == 0

    assert medidos == ["sw-001", "in-001"]
    assert Referencia.ler(saida).personas["davi"].episodios == ("in-001", "sw-001")


def test_comando_referencia_recusa_o_que_nao_e_id_de_episodio():
    with pytest.raises(SystemExit):
        qv.main(["referencia", "--repo", "d/r", "--episodios", "sw-001;rm"])


def test_referencia_versionada_cobre_as_personas_com_o_modelo_da_config():
    import yaml

    raiz = Path(__file__).parent.parent
    config = yaml.safe_load((raiz / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    referencia = Referencia.ler(raiz / "config" / "vozes-referencia.json")

    assert referencia.modelo_sha256 == config["qa_voz"]["modelo"]["sha256"]
    assert set(referencia.personas) == {"beatriz", "camila", "davi", "helena", "jorge", "otavio", "rafael", "yasmin"}


# Modelo


def test_modelo_com_sha_errado_nao_fica_no_cache_nem_e_carregado(tmp_path):
    def baixar(url, destino):
        destino.write_bytes(b"outro arquivo")

    with pytest.raises(ModeloIndisponivel, match="SHA-256"):
        obter_modelo(Modelo("https://modelo", SHA), tmp_path, baixar)

    assert list(tmp_path.iterdir()) == []


def test_modelo_conferido_vai_para_o_cache_pelo_sha(tmp_path):
    conteudo = b"pesos do modelo"
    sha = __import__("hashlib").sha256(conteudo).hexdigest()
    baixados = []

    def baixar(url, destino):
        baixados.append(url)
        destino.write_bytes(conteudo)

    primeiro = obter_modelo(Modelo("https://modelo", sha), tmp_path, baixar)
    segundo = obter_modelo(Modelo("https://modelo", sha), tmp_path, baixar)

    assert primeiro == segundo == tmp_path / f"{sha}.onnx"
    assert baixados == ["https://modelo"]


def test_modelo_do_cache_adulterado_e_baixado_de_novo(tmp_path):
    conteudo = b"pesos do modelo"
    sha = __import__("hashlib").sha256(conteudo).hexdigest()
    (tmp_path / f"{sha}.onnx").write_bytes(b"adulterado")

    obter_modelo(Modelo("https://modelo", sha), tmp_path, lambda url, destino: destino.write_bytes(conteudo))

    assert (tmp_path / f"{sha}.onnx").read_bytes() == conteudo


def test_download_falho_vira_modelo_indisponivel(tmp_path):
    def baixar(url, destino):
        raise OSError("sem rede")

    with pytest.raises(ModeloIndisponivel, match="não baixou"):
        obter_modelo(Modelo("https://modelo", SHA), tmp_path, baixar)


@precisa_ffmpeg
def test_sha_errado_na_publicacao_vira_qa_de_voz_nao_rodou_e_o_episodio_sai(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    carregados = []

    def obter(modelo):
        raise ModeloIndisponivel("o modelo baixado tem SHA-256 errado")

    qa = _qa(obter=obter, criar_embedder=carregados.append)
    resultado = publicar_pendentes(projeto, ReleasesFalso(), lambda nome: ProvedorFalso(nome), tmp_path, qa_voz=qa)

    assert resultado.publicados == ["sw-001"]
    assert "QA de voz não rodou" in resultado.voz_nao_rodou["sw-001"] and "SHA-256" in resultado.voz_nao_rodou["sw-001"]
    assert carregados == []


# Kokoro


@precisa_ffmpeg
def test_episodio_no_fallback_tem_laudo_nao_aplicavel_e_nada_e_aberto(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    gh = GhFalso()

    def obter(modelo):
        raise AssertionError("o fallback não pode nem baixar o modelo")

    qa = _qa(obter=obter, incidentes=IncidentesDeVoz("dono/repo", None, gh))

    def criar(nome):
        return ProvedorQuebrado() if nome == "gemini-falso" else ProvedorFalso(nome)

    resultado = publicar_pendentes(projeto, ReleasesFalso(), criar, tmp_path, qa_voz=qa)

    laudo = resultado.voz["sw-001"]
    assert not laudo.aplicavel and "fallback" in laudo.markdown("Voz do sw-001")
    assert "não aplicável" in laudo.markdown("Voz do sw-001")
    assert gh.comandos == []


# Incidente

TITULO = "Voz do sw-002 fora do padrão"
REPROVADO = avaliar(_episodio(helena=DAVI), PERSONAS, {}, {}, LimitesDeVoz())
APROVADO = avaliar(_episodio(), PERSONAS, {}, {}, LimitesDeVoz())


def test_voz_reprovada_abre_issue_incidente_com_o_laudo():
    gh = GhFalso()

    IncidentesDeVoz("dono/repo", "https://run/1", gh).registrar("sw-002", REPROVADO)

    [criar] = gh.acoes()
    assert criar[:3] == ["gh", "issue", "create"]
    assert criar[criar.index("--title") + 1] == TITULO
    assert criar[criar.index("--label") + 1] == "incidente"
    corpo = criar[criar.index("--body") + 1]
    assert "soam como a mesma voz" in corpo and "alarme falso" in corpo and "https://run/1" in corpo


def test_voz_reprovada_de_novo_so_comenta():
    gh = GhFalso([{"number": 50, "title": TITULO}])

    IncidentesDeVoz("dono/repo", None, gh).registrar("sw-002", REPROVADO)

    [comentar] = gh.acoes()
    assert comentar[:4] == ["gh", "issue", "comment", "50"]


def test_voz_aprovada_fecha_a_issue():
    gh = GhFalso([{"number": 50, "title": TITULO}, {"number": 9, "title": "Áudio do sw-002 fora do padrão"}])

    IncidentesDeVoz("dono/repo", None, gh).registrar("sw-002", APROVADO)

    [fechar] = gh.acoes()
    assert fechar[:4] == ["gh", "issue", "close", "50"]


def test_titulo_nao_termina_com_o_id_para_o_publicar_nao_fechar_como_roteiro():
    assert not IncidentesDeVoz.titulo("sw-002").endswith(": sw-002")


def test_laudo_de_voz_vai_e_volta_em_json():
    assert LaudoDeVoz.de_json(REPROVADO.para_json()) == REPROVADO


# Modo regravar


@pytest.mark.parametrize(("modo", "publicados", "aguardando", "laudos", "esperado"), [
    ("regravar", ["sw-002"], [], {"sw-002": REPROVADO}, ["sw-002"]),
    ("aviso", ["sw-002"], [], {"sw-002": REPROVADO}, []),
    ("regravar", ["sw-002"], ["in-002"], {"sw-002": REPROVADO}, []),
    ("regravar", ["sw-002", "in-002"], [], {"sw-002": REPROVADO, "in-002": REPROVADO}, []),
    ("regravar", ["sw-002"], [], {"sw-002": APROVADO}, []),
    ("regravar", ["sw-002"], [], {"sw-002": LaudoDeVoz(nao_aplicavel="fallback")}, []),
    ("regravar", ["sw-002"], [], {}, []),
])
def test_quem_a_publicacao_manda_regravar(modo, publicados, aguardando, laudos, esperado):
    assert a_regravar(modo, publicados, aguardando, laudos) == esperado


def test_disparo_roda_o_regravar_uma_vez_e_comenta_na_issue():
    gh = GhFalso([{"number": 50, "title": TITULO}])

    disparar_regravacao(["sw-002"], "dono/repo", IncidentesDeVoz("dono/repo", None, gh), gh)

    workflow, comentario = gh.acoes()
    assert workflow == ["gh", "workflow", "run", "regravar.yml", "-f", "episodio=sw-002", "-f", "acao=regravar",
                        "--repo", "dono/repo"]
    assert comentario[:4] == ["gh", "issue", "comment", "50"]


def test_disparo_recusa_id_que_nao_e_de_episodio():
    gh = GhFalso()

    with pytest.raises(ValueError):
        disparar_regravacao(["sw-002 -f acao=substituir"], "dono/repo", IncidentesDeVoz("dono/repo", None, gh), gh)
    assert gh.comandos == []


def test_comando_disparar_le_o_relatorio_da_publicacao(tmp_path, monkeypatch):
    disparos = []
    monkeypatch.setattr(qv, "disparar_regravacao", lambda ids, repo, incidentes: disparos.append(list(ids)) or ids)
    arquivo = tmp_path / "relatorio.json"
    arquivo.write_text(json.dumps({"publicados": ["sw-002"], "regravar_automatico": []}), encoding="utf-8")

    qv.main(["disparar", "--repo", "d/r", "--relatorio", str(arquivo)])

    assert disparos == [[]]


class QaDeVozFalso:
    """Devolve o laudo pedido sem medir nada; guarda quem foi medido."""

    def __init__(self, laudo: LaudoDeVoz, modo: str = "regravar") -> None:
        self.laudo, self.modo, self.medidos = laudo, modo, []

    def rodar(self, episodio_id, mp3, trechos, falas, fallback=False):
        self.medidos.append(episodio_id)
        return LaudoDeVoz(nao_aplicavel="fallback") if fallback else self.laudo

    def medir(self, mp3, trechos, falas):
        self.medidos.append(mp3.name)
        return self.laudo


@precisa_ffmpeg
def test_publicacao_com_voz_reprovada_no_modo_regravar_pede_uma_regravacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")

    resultado = publicar_pendentes(projeto, ReleasesFalso(), lambda nome: ProvedorFalso(nome), tmp_path,
                                   qa_voz=QaDeVozFalso(REPROVADO))

    assert resultado.regravar_automatico == ["sw-001"]
    assert relatorio(resultado)["regravar_automatico"] == ["sw-001"]


@precisa_ffmpeg
def test_publicacao_no_modo_aviso_nao_pede_regravacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")

    resultado = publicar_pendentes(projeto, ReleasesFalso(), lambda nome: ProvedorFalso(nome), tmp_path,
                                   qa_voz=QaDeVozFalso(REPROVADO, modo="aviso"))

    assert resultado.regravar_automatico == []


@precisa_ffmpeg
def test_publicacao_com_episodio_aguardando_a_cota_nao_pede_regravacao(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    _escrever_episodio(projeto, "sw-002")

    chamadas = []

    class SemCotaNoSegundo:
        """O primeiro episódio sai; o segundo encontra a cota diária esgotada."""

        def __init__(self, nome):
            self.nome = nome

        def sintetizar(self, falas):
            chamadas.append(self.nome)
            if len(chamadas) > 1:
                raise CotaDiariaEsgotada("PerDay")
            return ProvedorFalso(self.nome).sintetizar(falas)

    resultado = publicar_pendentes(projeto, ReleasesFalso(), SemCotaNoSegundo, tmp_path, qa_voz=QaDeVozFalso(REPROVADO))

    assert resultado.publicados == ["sw-001"] and resultado.aguardando == ["sw-002"]
    assert resultado.regravar_automatico == []


# Regravação


@precisa_ffmpeg
@pytest.mark.parametrize(("laudo", "esperado"), [(APROVADO, "aprovada"), (REPROVADO, "também reprovou")])
def test_regravacao_mede_a_candidata_e_comenta_na_issue_de_voz(projeto, tmp_path, laudo, esperado):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    gh = GhFalso([{"number": 50, "title": "Voz do sw-001 fora do padrão"}])
    qa = QaDeVozFalso(laudo)

    candidata = regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho", qa_voz=qa,
                         incidentes_voz=IncidentesDeVoz("dono/repo", None, gh))

    assert qa.medidos == ["pebacast-sw-001-candidata.mp3"]
    assert candidata.voz == laudo
    assert "pebacast-sw-001-candidata.voz.json" in releases.assets["sw-001"]
    [comentario] = gh.acoes()
    assert comentario[:4] == ["gh", "issue", "comment", "50"]
    assert esperado in comentario[comentario.index("--body") + 1]
    # Só a publicação dispara regravação: a candidata reprovada não chama o regravar.yml.
    assert not any(comando[1:2] == ["workflow"] for comando in gh.comandos)


@precisa_ffmpeg
def test_regravacao_com_a_cota_esgotada_comenta_que_precisa_rodar_a_mao(projeto, tmp_path):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    gh = GhFalso([{"number": 50, "title": "Voz do sw-001 fora do padrão"}])

    class SemCota:
        nome = "gemini-3.8-flash-tts"

        def sintetizar(self, falas):
            raise CotaDiariaEsgotada("PerDay")

    with pytest.raises(RegravacaoInvalida, match="cota"):
        regravar(projeto, "sw-001", releases, lambda nome: SemCota(), tmp_path / "trabalho",
                 qa_voz=QaDeVozFalso(REPROVADO), incidentes_voz=IncidentesDeVoz("dono/repo", None, gh))

    [comentario] = gh.acoes()
    assert COMENTARIO_DE_COTA in comentario[comentario.index("--body") + 1]


@precisa_ffmpeg
@pytest.mark.parametrize(("laudo", "acao"), [(APROVADO, "close"), (REPROVADO, "comment")])
def test_substituir_le_o_laudo_de_voz_salvo_e_atualiza_a_issue(projeto, tmp_path, laudo, acao):
    releases = ReleasesFalso()
    _ja_publicado(projeto, tmp_path, releases)
    regravar(projeto, "sw-001", releases, _fabrica(), tmp_path / "trabalho", qa_voz=QaDeVozFalso(laudo))
    gh = GhFalso([{"number": 50, "title": "Voz do sw-001 fora do padrão"}])

    substituicao = substituir(projeto, "sw-001", releases, tmp_path / "troca", incidentes_voz=IncidentesDeVoz("d/r", None, gh))

    assert substituicao.voz == laudo
    [comando] = gh.acoes()
    assert comando[:4] == ["gh", "issue", acao, "50"]
    assert "pebacast-sw-001-candidata.voz.json" not in releases.assets["sw-001"]


# Segmentação


def test_segmentacao_corta_nas_pausas_certas_pela_duracao_esperada():
    taxa = qv.TAXA
    trechos = [(1.0, 0.4), (3.0, 0.4), (1.5, 0.4), (4.0, 0.4)]  # (fala em s, pausa em s)
    partes = [np.zeros(int(0.5 * taxa))]
    for fala, pausa in trechos:
        tempo = np.arange(int(fala * taxa)) / taxa
        partes += [0.3 * np.sin(2 * np.pi * 200 * tempo), np.zeros(int(pausa * taxa))]
    x = np.concatenate(partes).astype(np.float32)
    # Uma pausa curta no meio do turno longo, que não pode virar corte.
    meio = int((0.5 + 1.4 + 1.5) * taxa)
    x[meio:meio + int(0.15 * taxa)] = 0
    turnos = [qv.Turno(i, p, 0, c) for i, (p, c) in enumerate([("davi", 14), ("helena", 48), ("davi", 22), ("helena", 64)])]

    qv.segmentar(x, turnos, (0.5, len(x) / taxa), None)

    fins = [round(t.fim, 1) for t in turnos[:-1]]
    assert fins == [pytest.approx(1.7, abs=0.15), pytest.approx(5.1, abs=0.15), pytest.approx(7.0, abs=0.15)]
    assert turnos[0].miolo is None  # o primeiro turno fica sob a vinheta


def test_trechos_de_episodio_publicado_saem_da_config_da_vinheta(tmp_path, monkeypatch):
    monkeypatch.setattr(qv, "duracao_mp3", lambda mp3: 600.0)
    config = {"vinheta": {"arquivo": "assets/vinheta.mp3", "sobreposicao_s": 1.5,
                          "abertura": {"inicio_s": 1, "duracao_s": 9, "fade_entrada_s": 0.3, "fade_saida_s": 3},
                          "encerramento": {"inicio_s": 85, "duracao_s": 11, "fade_entrada_s": 1, "fade_saida_s": 0.5}}}

    assert qv.trechos_publicados(Path("e.mp3"), config, True) == Trechos(fala=(7.5, 589.0))
    assert qv.trechos_publicados(Path("e.mp3"), config, False) == Trechos(fala=(0.0, 600.0))


def test_turnos_seguem_os_blocos_da_sintese():
    from tests.conftest import criar_persona

    davi, helena = criar_persona("davi", "Davi"), criar_persona("helena", "Helena")
    falas = [Fala(davi if i % 2 == 0 else helena, "x" * 900) for i in range(6)]

    turnos = qv.turnos_das_falas(falas, 2000)

    assert [t.bloco for t in turnos] == [0, 0, 1, 1, 2, 2]
    assert [t.persona for t in turnos] == ["davi", "helena"] * 3


def test_de_config_recusa_modo_desconhecido(tmp_path):
    with pytest.raises(ValueError, match="qa_voz.modo"):
        QaDeVoz.de_config({"modo": "sempre", "modelo": {"url": "u", "sha256": SHA}}, {"max_caracteres_por_bloco": 4000},
                          PERSONAS, tmp_path / "nada.json")

