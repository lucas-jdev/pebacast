import json
from pathlib import Path

import yaml

from podcast.publicacao import episodios_aguardando_cota, main
from tests.test_roteiro import _escrever_episodio, projeto  # noqa: F401 (fixture)

RAIZ = Path(__file__).resolve().parents[1]


def _aguardando_cota(projeto, episodio):
    (projeto.episodios / episodio / "aguardando_cota.json").write_text(
        json.dumps({"desde": "2026-11-21T08:15:00+00:00"}), encoding="utf-8")


def _publicado(projeto, episodio):
    (projeto.episodios / episodio / "publicacao.json").write_text("{}", encoding="utf-8")


# Dado o que está na pasta de episódios, quando o agendamento lista o que retomar, então só vem o que aguarda a cota.


def test_roteiro_reprovado_parado_sem_ninguem_aguardando_deixa_a_lista_vazia(projeto):
    _escrever_episodio(projeto, "sw-001", revisoes=[])  # roteiro sem revisão aprovada: reprovado na validação

    assert episodios_aguardando_cota(projeto) == []


def test_episodio_com_aguardando_cota_entra_na_lista(projeto):
    _escrever_episodio(projeto, "sw-001")
    _escrever_episodio(projeto, "sw-002", revisoes=[])
    _aguardando_cota(projeto, "sw-001")

    assert episodios_aguardando_cota(projeto) == ["sw-001"]


def test_episodio_ja_publicado_com_aguardando_cota_por_engano_fica_fora(projeto):
    _escrever_episodio(projeto, "sw-001")
    _aguardando_cota(projeto, "sw-001")
    _publicado(projeto, "sw-001")

    assert episodios_aguardando_cota(projeto) == []


def test_sem_pasta_de_episodios_a_lista_sai_vazia(tmp_path):
    from podcast.roteiro import Projeto

    assert episodios_aguardando_cota(Projeto(tmp_path)) == []


def test_comando_aguardando_imprime_os_ids_separados_por_espaco(projeto, capsys):
    for episodio in ("sw-001", "sw-002"):
        _escrever_episodio(projeto, episodio)
        _aguardando_cota(projeto, episodio)

    assert main(["--raiz", str(projeto.raiz), "aguardando"]) == 0
    assert capsys.readouterr().out.strip() == "sw-001 sw-002"


def test_comando_aguardando_sem_nada_imprime_linha_vazia(projeto, capsys):
    _escrever_episodio(projeto, "sw-001", revisoes=[])

    assert main(["--raiz", str(projeto.raiz), "aguardando"]) == 0
    assert capsys.readouterr().out.strip() == ""


# Conferência do publicar.yml: o agendamento usa a lista; push e workflow_dispatch não passam por ela.


def _publicar_yml():
    return yaml.safe_load((RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8"))


def test_verificar_roda_so_no_agendamento_e_usa_a_lista_do_python():
    verificar = _publicar_yml()["jobs"]["verificar"]

    assert verificar["if"] == "${{ github.event_name == 'schedule' }}"
    comandos = "\n".join(passo.get("run", "") for passo in verificar["steps"])
    assert "python -m podcast.publicacao aguardando" in comandos
    assert "roteiro.json" not in comandos


def test_publicar_so_depende_da_lista_no_agendamento():
    workflow = _publicar_yml()
    condicao = workflow["jobs"]["publicar"]["if"]

    assert workflow[True]["schedule"]  # o yaml lê a chave "on" como True
    assert "push" in workflow[True] and "workflow_dispatch" in workflow[True]
    assert "github.event_name != 'schedule' || needs.verificar.outputs.aguardando != ''" in condicao
    # Sem isto, o verificar pulado no push e no workflow_dispatch pularia a publicação também.
    assert condicao.startswith("${{ !cancelled() &&")
