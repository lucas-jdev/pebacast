import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from podcast.roteiro import (
    AGUARDANDO_PUBLICACAO,
    PENDENTE,
    PUBLICADO,
    SAIDA_SEM_EPISODIO,
    Projeto,
    SemEpisodio,
    data_de_publicacao,
    estado_do_episodio,
    main,
    montar_contexto,
    ordem_da_fila,
    regras_para,
    saga_do_dia,
    selecionar,
)
from podcast.validacao import hash_do_roteiro, validar_episodio

RAIZ = Path(__file__).resolve().parents[1]
PALAVRAS_POR_FALA = 10

CONFIG = {
    "agenda": {
        "modo": "saga_unica",
        "saga_unica": "software",
        "fila": ["software", "solucoes", "seguranca"],
        "rotacao_semanal": {
            "segunda": "software", "terca": "solucoes", "quarta": "sistemas", "quinta": "dados",
            "sexta": "infraestrutura", "sabado": "seguranca", "domingo": "corporativa",
        },
    },
    "episodio": {"palavras_alvo": {"min": 20, "max": 60}, "idioma": "pt-BR", "exigir_referencias_verificadas": True},
    "noticias": {"janelas_dias": [7, 30, 60], "nota_minima_relevancia": 7, "fallback": "cenario_hipotetico"},
    "revisao": {"max_ciclos": 2, "vereditos_reprovam": ["incorreta", "imprecisa"], "falhar_fechado": True},
    "feedback": {"ultimos_por_saga": 2},
    "tts": {"principal": "gemini-falso", "fallback": "kokoro-falso"},
    "audio": {"bitrate_kbps": 64},
    "feed": {
        "titulo": "Pebacast", "descricao": "Podcast de teste.", "autor": "Lucas", "email_dono": "lucas@exemplo.com", "capa": "capa-kraft.jpg", "url_site": "https://x.github.io/pebacast/",
        "url_repositorio": "https://github.com/x/pebacast", "idioma": "pt-br", "categoria": "Technology", "licenca": "CC BY 4.0",
    },
}

SAGA = {
    "id": "software",
    "nome": "Arquitetura de Software",
    "pergunta_central": "Como um sistema é organizado por dentro?",
    "expert": "helena",
    "referencias_base": [{"id": "fosa", "titulo": "Fundamentals of Software Architecture", "tipo": "livro"}],
    "episodios": [
        {"id": "sw-001", "titulo": "Um", "pre_requisitos": [], "referencias": [{"fonte": "fosa", "capitulos": [1]}],
         "referencias_verificadas": True},
        {"id": "sw-002", "titulo": "Dois", "pre_requisitos": ["sw-001"], "referencias": [{"fonte": "fosa"}],
         "referencias_verificadas": True},
        {"id": "sw-003", "titulo": "Três", "pre_requisitos": ["sw-001"], "referencias": [{"fonte": "fosa"}],
         "referencias_verificadas": False},
    ],
}

VOZ = {"gemini": "Puck", "kokoro": "pm_alex", "piper": "pt_BR-faber-medium", "instrucao_de_estilo": "calmo"}
PERSONAS = [
    {"id": "davi", "nome": "Davi", "papel": "apresentador", "sagas": ["todas"], "voz": VOZ},
    {"id": "helena", "nome": "Helena", "papel": "expert", "sagas": ["software"], "voz": VOZ},
]


def _gravar(arquivo: Path, dados: object) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    if arquivo.suffix == ".json":
        arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    else:
        arquivo.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def projeto(tmp_path: Path) -> Projeto:
    _gravar(tmp_path / "config" / "pipeline.yaml", CONFIG)
    _gravar(tmp_path / "curriculum" / "sagas" / "software.yaml", SAGA)
    for persona in PERSONAS:
        _gravar(tmp_path / "curriculum" / "personas" / f"{persona['id']}.yaml", persona)
    (tmp_path / "episodios").mkdir()
    return Projeto(tmp_path)


def _roteiro(episodio: str, falas: int = 4) -> dict:
    texto = " ".join(["palavra"] * PALAVRAS_POR_FALA)
    corpo = [{"persona": "helena" if i % 2 else "davi", "texto": texto} for i in range(1, falas)]
    abertura = {"persona": "davi", "texto": "Bem-vindos ao Pebacast! Episódio gerado por IA. Hoje a convidada é a Helena."}
    return {"episodio": episodio, "falas": [abertura, *corpo], "desafio": "Liste dois trade-offs.", "fontes": ["fosa cap. 1"]}


def _revisao(roteiro: dict, aprovado: bool = True, veredito: str = "correta") -> dict:
    return {
        "aprovado": aprovado,
        "roteiro_sha256": hash_do_roteiro(roteiro),
        "afirmacoes": [{"fala": 1, "afirmacao": "palavra palavra", "veredito": veredito}],
    }


def _escrever_episodio(projeto: Projeto, episodio: str, **alteracoes: object) -> Path:
    pasta = projeto.episodios / episodio
    roteiro = alteracoes.get("roteiro", _roteiro(episodio))
    noticia = alteracoes.get("noticia", {"tipo": "hipotetico", "cenario": "Imagine uma empresa de logística."})
    revisoes = alteracoes.get("revisoes", [_revisao(roteiro)])
    _gravar(pasta / "roteiro.json", roteiro)
    _gravar(pasta / "noticia.json", noticia)
    for numero, revisao in enumerate(revisoes, start=1):
        _gravar(pasta / "revisoes" / f"{numero}.json", revisao)
    return pasta


def _publicar(projeto: Projeto, episodio: str, publicado_em: str = "2026-11-07T15:00:00+00:00") -> None:
    _escrever_episodio(projeto, episodio)
    _gravar(projeto.episodios / episodio / "publicacao.json", {"guid": episodio, "publicado_em": publicado_em})


def _usar_fila(projeto: Projeto) -> None:
    _gravar(projeto.raiz / "config" / "pipeline.yaml", {**CONFIG, "agenda": {**CONFIG["agenda"], "modo": "fila"}})
    sagas = (
        ("solucoes", "beatriz", [("sl-001", True), ("sl-002", False)]),
        ("seguranca", "yasmin", [("se-001", False)]),
    )
    for saga_id, expert, episodios in sagas:
        _gravar(projeto.raiz / "curriculum" / "sagas" / f"{saga_id}.yaml", {
            "id": saga_id, "nome": saga_id, "pergunta_central": "?", "expert": expert,
            "referencias_base": [{"id": "livro", "titulo": "Livro", "tipo": "livro"}],
            "episodios": [
                {"id": id_, "titulo": id_, "pre_requisitos": [], "referencias": [{"fonte": "livro"}],
                 "referencias_verificadas": verificado}
                for id_, verificado in episodios
            ],
        })
        persona = {"id": expert, "nome": expert.title(), "papel": "expert", "sagas": [saga_id], "voz": VOZ}
        _gravar(projeto.raiz / "curriculum" / "personas" / f"{expert}.yaml", persona)


def _problemas(projeto: Projeto, episodio: str) -> list[str]:
    saga = projeto.sagas()["software"]
    return validar_episodio(projeto.episodios / episodio, regras_para(projeto, saga, episodio))


# Agenda


def test_rotina_da_noite_escreve_o_episodio_do_dia_seguinte_no_horario_de_brasilia():
    # 01:30 UTC de 8/11 ainda é 22:30 de 7/11 em Brasília.
    assert data_de_publicacao(datetime(2026, 11, 8, 1, 30, tzinfo=timezone.utc)) == date(2026, 11, 8)


def test_rotacao_semanal_escolhe_a_saga_pelo_dia_da_publicacao():
    config = {**CONFIG, "agenda": {**CONFIG["agenda"], "modo": "rotacao_semanal"}}
    assert saga_do_dia(config, date(2026, 11, 10)) == "solucoes"  # terça
    assert saga_do_dia(CONFIG, date(2026, 11, 10)) == "software"


# Seleção


def test_seleciona_o_primeiro_episodio_pendente(projeto):
    assert montar_contexto(projeto, date(2026, 11, 8))["episodio"]["id"] == "sw-001"


def test_pre_requisito_so_conta_depois_de_publicado(projeto):
    saga_bloqueada = {**SAGA, "episodios": [{**SAGA["episodios"][0], "referencias_verificadas": False}, *SAGA["episodios"][1:]]}
    _gravar(projeto.raiz / "curriculum" / "sagas" / "software.yaml", saga_bloqueada)

    with pytest.raises(SemEpisodio, match=r"sw-002: pré-requisitos não publicados \(sw-001\)"):
        selecionar(projeto.sagas()["software"], {"sw-001": PENDENTE}, exigir_referencias_verificadas=True)

    saga = projeto.sagas()["software"]
    assert selecionar(saga, {"sw-001": PUBLICADO}, exigir_referencias_verificadas=True).id == "sw-002"


def test_pula_episodio_com_referencias_nao_verificadas(projeto):
    saga = projeto.sagas()["software"]
    estados = {"sw-001": PUBLICADO, "sw-002": PUBLICADO}
    with pytest.raises(SemEpisodio, match="sw-003: referências não verificadas"):
        selecionar(saga, estados, exigir_referencias_verificadas=True)
    assert selecionar(saga, estados, exigir_referencias_verificadas=False).id == "sw-003"


def test_nao_escreve_novo_roteiro_enquanto_outro_aguarda_publicacao(projeto):
    _escrever_episodio(projeto, "sw-001")
    assert estado_do_episodio(projeto, projeto.sagas()["software"], "sw-001") == AGUARDANDO_PUBLICACAO
    with pytest.raises(SemEpisodio, match="sw-001 já tem roteiro aprovado"):
        montar_contexto(projeto, date(2026, 11, 8))


def test_ordem_da_fila_poe_saga_nunca_publicada_antes_e_respeita_a_fila_nos_empates():
    ultimas = {"software": "2026-11-09T22:00:00+00:00", "solucoes": "2026-11-07T15:00:00+00:00"}
    assert ordem_da_fila(["software", "solucoes", "dados", "seguranca"], ultimas) == [
        "dados", "seguranca", "solucoes", "software",
    ]


def test_fila_comeca_pela_saga_que_nunca_foi_publicada(projeto):
    _usar_fila(projeto)
    _publicar(projeto, "sw-001")

    contexto = montar_contexto(projeto, date(2026, 11, 8))

    assert contexto["episodio"]["id"] == "sl-001"
    assert contexto["personas"]["expert"]["id"] == "beatriz"


def test_fila_pula_saga_sem_episodio_verificado_e_volta_a_publicada_ha_mais_tempo(projeto):
    _usar_fila(projeto)
    _publicar(projeto, "sw-001", publicado_em="2026-11-07T15:00:00+00:00")
    _publicar(projeto, "sl-001", publicado_em="2026-11-09T15:00:00+00:00")

    assert montar_contexto(projeto, date(2026, 11, 10))["episodio"]["id"] == "sw-002"


def test_fila_nao_escreve_novo_roteiro_enquanto_qualquer_saga_aguarda_publicacao(projeto):
    _usar_fila(projeto)
    _escrever_episodio(projeto, "sw-001")
    with pytest.raises(SemEpisodio, match="sw-001 já tem roteiro aprovado"):
        montar_contexto(projeto, date(2026, 11, 8))


def test_fila_sem_episodio_explica_o_motivo_de_cada_saga(projeto):
    _usar_fila(projeto)
    for episodio in ("sw-001", "sw-002", "sl-001"):
        _publicar(projeto, episodio)

    with pytest.raises(SemEpisodio) as erro:
        montar_contexto(projeto, date(2026, 11, 8))

    for trecho in ("sw-003: referências não verificadas", "sl-002: referências não verificadas",
                   "se-001: referências não verificadas"):
        assert trecho in str(erro.value)


def test_tentativa_reprovada_volta_para_a_fila(projeto):
    roteiro = _roteiro("sw-001")
    _escrever_episodio(projeto, "sw-001", revisoes=[_revisao(roteiro, aprovado=False, veredito="incorreta")])
    assert estado_do_episodio(projeto, projeto.sagas()["software"], "sw-001") == PENDENTE
    assert montar_contexto(projeto, date(2026, 11, 8))["episodio"]["id"] == "sw-001"


def test_contexto_traz_referencias_resolvidas_personas_e_feedbacks_recentes(projeto):
    _publicar(projeto, "sw-001")
    for dia in (1, 2, 3):
        _gravar(projeto.raiz / "feedback" / "software" / f"f{dia}.yaml", {"ouvido_em": date(2026, 11, dia), "nota": dia})

    contexto = montar_contexto(projeto, date(2026, 11, 8))

    assert contexto["episodio"]["id"] == "sw-002"
    assert contexto["pasta"] == "episodios/sw-002"
    assert contexto["referencias"][0]["titulo"] == "Fundamentals of Software Architecture"
    assert contexto["personas"]["apresentador"]["id"] == "davi"
    assert contexto["personas"]["expert"]["id"] == "helena"
    assert [f["nota"] for f in contexto["feedbacks_recentes"]] == [3, 2]
    assert contexto["regras"]["revisao"]["max_revisoes"] == 3


def test_contexto_lista_noticias_usadas_por_outros_episodios(projeto):
    noticia = {"tipo": "noticia", "titulo": "t", "url": "https://x/1", "fonte": "f", "data": "2026-11-01",
               "nota_relevancia": 8, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _gravar(projeto.episodios / "sw-001" / "publicacao.json", {})

    assert montar_contexto(projeto, date(2026, 11, 8))["noticias_ja_usadas"] == ["https://x/1"]


# Validação


def test_episodio_completo_e_aprovado_passa(projeto):
    _escrever_episodio(projeto, "sw-001")
    assert _problemas(projeto, "sw-001") == []


def test_roteiro_alterado_depois_da_revisao_e_reprovado(projeto):
    pasta = _escrever_episodio(projeto, "sw-001")
    roteiro = _roteiro("sw-001")
    roteiro["falas"][1]["texto"] += " frase nova"
    _gravar(pasta / "roteiro.json", roteiro)

    assert any("mudou depois da última revisão" in p for p in _problemas(projeto, "sw-001"))


def test_hash_ignora_formatacao_do_json():
    roteiro = _roteiro("sw-001")
    reformatado = json.loads(json.dumps(roteiro, indent=4))
    assert hash_do_roteiro(roteiro) == hash_do_roteiro(reformatado)


def test_aprovacao_com_afirmacao_incorreta_e_inconsistente(projeto):
    roteiro = _roteiro("sw-001")
    _escrever_episodio(projeto, "sw-001", revisoes=[_revisao(roteiro, aprovado=True, veredito="imprecisa")])
    assert any("marcada como aprovada" in p for p in _problemas(projeto, "sw-001"))


def test_reprova_depois_do_limite_de_ciclos(projeto):
    roteiro = _roteiro("sw-001")
    reprovada = _revisao(roteiro, aprovado=False, veredito="incorreta")
    _escrever_episodio(projeto, "sw-001", revisoes=[reprovada, reprovada, reprovada, _revisao(roteiro)])
    assert any("acima do limite de 3" in p for p in _problemas(projeto, "sw-001"))


def test_aceita_aprovacao_na_terceira_revisao(projeto):
    roteiro = _roteiro("sw-001")
    reprovada = _revisao(roteiro, aprovado=False, veredito="incorreta")
    _escrever_episodio(projeto, "sw-001", revisoes=[reprovada, reprovada, _revisao(roteiro)])
    assert _problemas(projeto, "sw-001") == []


@pytest.mark.parametrize(
    ("alterar", "trecho"),
    [
        (lambda r: r["falas"].insert(0, {"persona": "helena", "texto": "Oi, IA."}), "primeira fala precisa ser do apresentador"),
        (lambda r: r["falas"][0].update(texto="Bem-vindos ao Pebacast. Hoje com a Helena."), "aviso de conteúdo gerado por IA"),
        (lambda r: r["falas"][0].update(texto="Episódio gerado por IA, com a Helena."), "apresentar o Pebacast"),
        (lambda r: r["falas"][0].update(texto="Bem-vindos ao Pebacast, episódio gerado por IA."), "apresentar Helena pelo nome"),
        (lambda r: r["falas"].insert(1, {"persona": "davi", "texto": "Antes de tudo, um recado rápido."}) or
                   r["falas"].insert(1, {"persona": "davi", "texto": "E mais um recado."}), "Helena precisa falar"),
        (lambda r: r["falas"].append({"persona": "bruno", "texto": "oi"}), "persona 'bruno' fora do episódio"),
        (lambda r: r.update(desafio=" "), "desafio vazio"),
        (lambda r: r.update(fontes=[]), "fontes precisa ser"),
        (lambda r: r.update(episodio="sw-002"), "esperado 'sw-001'"),
        (lambda r: r["falas"].extend(r["falas"][1:] * 3), "fora da faixa 20-60"),
    ],
)
def test_problemas_no_roteiro(projeto, alterar, trecho):
    roteiro = _roteiro("sw-001")
    alterar(roteiro)
    _escrever_episodio(projeto, "sw-001", roteiro=roteiro, revisoes=[_revisao(roteiro)])
    assert any(trecho in p for p in _problemas(projeto, "sw-001")), _problemas(projeto, "sw-001")


def test_noticia_abaixo_da_nota_minima_e_reprovada(projeto):
    noticia = {"tipo": "noticia", "titulo": "t", "url": "https://x/1", "fonte": "f", "data": "2026-11-01",
               "nota_relevancia": 6, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    assert any("abaixo do mínimo 7" in p for p in _problemas(projeto, "sw-001"))


def test_noticia_repetida_e_reprovada(projeto):
    noticia = {"tipo": "noticia", "titulo": "t", "url": "https://x/1", "fonte": "f", "data": "2026-11-01",
               "nota_relevancia": 9, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _escrever_episodio(projeto, "sw-002", noticia=noticia)
    assert _problemas(projeto, "sw-002") == []  # sw-001 ainda não foi publicado

    _gravar(projeto.episodios / "sw-001" / "publicacao.json", {})
    assert any("já usada" in p for p in _problemas(projeto, "sw-002"))
    assert _problemas(projeto, "sw-001") == []


def test_sem_revisao_e_reprovado(projeto):
    _escrever_episodio(projeto, "sw-001", revisoes=[])
    assert _problemas(projeto, "sw-001") == ["revisoes/: nenhuma revisão encontrada"]


def test_afirmacao_apontando_para_fala_inexistente(projeto):
    roteiro = _roteiro("sw-001")
    revisao = _revisao(roteiro)
    revisao["afirmacoes"][0]["fala"] = 99
    _escrever_episodio(projeto, "sw-001", revisoes=[revisao])
    assert any("fala inexistente" in p for p in _problemas(projeto, "sw-001"))


def test_afirmacao_que_nao_esta_na_fala_indicada(projeto):
    roteiro = _roteiro("sw-001")
    roteiro["falas"][2]["texto"] += " Toda decisão é trade-off."
    revisao = _revisao(roteiro)
    revisao["afirmacoes"][0].update(fala=1, afirmacao="toda decisão é trade-off")
    _escrever_episodio(projeto, "sw-001", revisoes=[revisao])
    assert any("não aparece na fala 1" in p for p in _problemas(projeto, "sw-001"))


def test_afirmacao_com_omissao_e_pontuacao_diferente_nas_pontas(projeto):
    roteiro = _roteiro("sw-001")
    roteiro["falas"][1]["texto"] = "Primeiro: tudo é trade-off. Depois vem   o resto. E o porquê vale mais que o como, sempre."
    revisao = _revisao(roteiro)
    revisao["afirmacoes"][0]["afirmacao"] = "Tudo é trade-off. [...] e o porquê vale mais que o como."
    _escrever_episodio(projeto, "sw-001", roteiro=roteiro, revisoes=[revisao])
    assert not any("não aparece" in p for p in _problemas(projeto, "sw-001"))


def test_so_a_revisao_final_confere_o_trecho(projeto):
    roteiro = _roteiro("sw-001")
    antiga = _revisao(roteiro, aprovado=False, veredito="imprecisa")
    antiga["afirmacoes"][0]["afirmacao"] = "frase de uma versão anterior do roteiro"
    _escrever_episodio(projeto, "sw-001", revisoes=[antiga, _revisao(roteiro)])
    assert _problemas(projeto, "sw-001") == []


# Linha de comando


def test_cli_sem_episodio_sai_com_codigo_proprio(projeto, capsys):
    _escrever_episodio(projeto, "sw-001")
    assert main(["--raiz", str(projeto.raiz), "contexto", "--data", "2026-11-08"]) == SAIDA_SEM_EPISODIO
    assert "aguarda publicação" in capsys.readouterr().err


def test_cli_validar(projeto, capsys):
    _escrever_episodio(projeto, "sw-001")
    assert main(["--raiz", str(projeto.raiz), "validar", "sw-001"]) == 0
    assert "Roteiro aprovado." in capsys.readouterr().out


def test_cli_hash_confere_com_o_da_validacao(projeto, capsys):
    _escrever_episodio(projeto, "sw-001")
    main(["--raiz", str(projeto.raiz), "hash", "sw-001"])
    assert capsys.readouterr().out.strip() == hash_do_roteiro(_roteiro("sw-001"))


def test_curriculo_real_comeca_pelo_sw_001(tmp_path):
    for pasta in ("config", "curriculum"):
        shutil.copytree(RAIZ / pasta, tmp_path / pasta)
    contexto = montar_contexto(Projeto(tmp_path), date(2026, 11, 8))
    assert contexto["episodio"]["id"] == "sw-001"
    assert contexto["personas"]["expert"]["id"] == "helena"
