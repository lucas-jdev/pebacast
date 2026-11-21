import json
import subprocess

from podcast.avisos import Aviso, IncidentesDeAvisos, encaminhar_avisos
from podcast.publicacao import Resultado, relatorio
from tests.test_publicacao import _configurar_vinheta, _fabrica, _publicar, precisa_ffmpeg
from tests.test_qualidade_audio import GhFalso
from tests.test_roteiro import _escrever_episodio, projeto  # noqa: F401 (fixture)

TITULO = "Avisos na publicação do sw-001"


def _encaminhar(avisos, tmp_path, gh):
    arquivo = tmp_path / "avisos.md"
    encaminhar_avisos(avisos, arquivo, IncidentesDeAvisos("dono/repo", "https://run/1", gh))
    return arquivo


def _issues_criadas(gh):
    return [comando for comando in gh.acoes() if comando[1:3] == ["issue", "create"]]


def _argumento(comando, nome):
    return comando[comando.index(nome) + 1]


# Dado uma publicação, quando os avisos são encaminhados, então cada tipo vai para a sua issue.


@precisa_ffmpeg
def test_publicacao_no_fallback_vai_so_para_a_issue_de_fallback(projeto, tmp_path):
    _escrever_episodio(projeto, "sw-001")
    resultado = _publicar(projeto, tmp_path, _fabrica(quebrar={"gemini-falso"}))
    gh = GhFalso()

    arquivo = _encaminhar(resultado.avisos, tmp_path, gh)

    [linha] = arquivo.read_text(encoding="utf-8").splitlines()
    assert linha.startswith("- sw-001: sintetizado com o fallback kokoro-falso.")
    assert gh.comandos == []


@precisa_ffmpeg
def test_publicacao_no_gemini_sem_vinheta_abre_a_issue_de_avisos_e_nao_a_de_fallback(projeto, tmp_path):
    _configurar_vinheta(projeto)
    _escrever_episodio(projeto, "sw-001")
    resultado = _publicar(projeto, tmp_path)
    gh = GhFalso()

    arquivo = _encaminhar(resultado.avisos, tmp_path, gh)

    assert not arquivo.exists()
    [criar] = _issues_criadas(gh)
    assert _argumento(criar, "--title") == TITULO
    assert _argumento(criar, "--label") == "incidente"
    corpo = _argumento(criar, "--body")
    assert "- publicado sem vinheta." in corpo and "VINHETA_SENHA" in corpo and "https://run/1" in corpo
    assert "fallback" not in corpo


@precisa_ffmpeg
def test_fallback_e_sem_vinheta_abrem_as_duas_issues_cada_uma_com_o_seu_aviso(projeto, tmp_path):
    _configurar_vinheta(projeto)
    _escrever_episodio(projeto, "sw-001")
    resultado = _publicar(projeto, tmp_path, _fabrica(quebrar={"gemini-falso"}))
    gh = GhFalso()

    arquivo = _encaminhar(resultado.avisos, tmp_path, gh)

    fallback = arquivo.read_text(encoding="utf-8")
    assert "sintetizado com o fallback" in fallback and "vinheta" not in fallback
    [criar] = _issues_criadas(gh)
    corpo = _argumento(criar, "--body")
    assert _argumento(criar, "--title") == TITULO
    assert "publicado sem vinheta" in corpo and "sintetizado com o fallback" not in corpo


def test_qa_que_nao_rodou_e_issue_da_cota_vao_para_a_mesma_issue_de_avisos(tmp_path):
    avisos = [
        Aviso("sw-001", "publicado, mas o QA do áudio não rodou até o fim. RuntimeError: ffmpeg"),
        Aviso("sw-001", "a issue da cota esgotada não foi fechada. CalledProcessError: gh"),
        Aviso("sw-002", "a issue da cota esgotada não foi aberta. CalledProcessError: gh"),
    ]
    gh = GhFalso()

    arquivo = _encaminhar(avisos, tmp_path, gh)

    assert not arquivo.exists()
    sw001, sw002 = _issues_criadas(gh)
    assert _argumento(sw001, "--title") == TITULO
    assert "QA do áudio não rodou" in _argumento(sw001, "--body")
    assert "não foi fechada" in _argumento(sw001, "--body")
    assert _argumento(sw002, "--title") == "Avisos na publicação do sw-002"


def test_com_a_issue_de_avisos_aberta_um_novo_aviso_so_comenta(tmp_path):
    gh = GhFalso([{"number": 42, "title": TITULO}])

    _encaminhar([Aviso("sw-001", "publicado sem vinheta. Falta o arquivo.")], tmp_path, gh)

    [comentar] = gh.acoes()
    assert comentar[:4] == ["gh", "issue", "comment", "42"]
    assert "publicado sem vinheta" in _argumento(comentar, "--body")


def test_titulo_da_issue_de_avisos_nao_termina_em_dois_pontos_e_id():
    # O passo "Atualizar issues" do publicar.yml fecha as issues que terminam em ": <id>".
    assert not IncidentesDeAvisos.titulo("sw-001").endswith(": sw-001")


def test_falha_do_gh_ao_abrir_a_issue_de_avisos_nao_derruba_a_publicacao(tmp_path, capsys):
    def gh_quebrado(comando, **_):
        raise subprocess.CalledProcessError(1, comando)

    _encaminhar([Aviso("sw-001", "publicado sem vinheta.")], tmp_path, gh_quebrado)

    assert "::warning::sw-001: a issue de avisos não foi aberta" in capsys.readouterr().out


def test_relatorio_separa_os_avisos_de_fallback_dos_outros():
    resultado = Resultado(publicados=["sw-001"], reprovados={}, avisos=[
        Aviso("sw-001", "sintetizado com o fallback kokoro.", fallback=True),
        Aviso("sw-001", "publicado sem vinheta."),
    ])

    dados = json.loads(json.dumps(relatorio(resultado)))

    assert dados["avisos"] == {"fallback": ["sw-001: sintetizado com o fallback kokoro."],
                               "outros": ["sw-001: publicado sem vinheta."]}
