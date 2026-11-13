from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# As sete sagas, na ordem do site, com nome curto e pergunta central (docs/fronteiras-das-sagas.md).
SAGAS = (
    ("software", "Software", "Como um sistema é organizado por dentro e por quê?"),
    ("solucoes", "Soluções", "Quais peças resolvem este problema de negócio e como elas se conectam?"),
    ("sistemas", "Sistemas", "Como as partes se comportam juntas, principalmente quando algo falha?"),
    ("dados", "Dados e Informação", "Como a informação é modelada, governada e flui pela organização?"),
    ("infraestrutura", "Infraestrutura", "Onde e como tudo isso roda, com qual custo e confiabilidade?"),
    ("seguranca", "Segurança", "Quem pode fazer o quê, e o que acontece quando alguém tenta o que não deveria?"),
    ("corporativa", "Corporativa", "Como a tecnologia sustenta a estratégia da organização?"),
)


@dataclass(frozen=True)
class Episodio:
    id: str
    titulo: str
    pre_requisitos: tuple[str, ...]
    referencias_verificadas: bool
    dados: dict[str, Any]


@dataclass(frozen=True)
class Saga:
    id: str
    nome: str
    expert: str
    episodios: tuple[Episodio, ...]
    dados: dict[str, Any]

    def episodio(self, id_: str) -> Episodio:
        for episodio in self.episodios:
            if episodio.id == id_:
                return episodio
        raise KeyError(f"Episódio {id_} não existe na saga {self.id}.")

    @property
    def nome_curto(self) -> str:
        return next((nome for sid, nome, _ in SAGAS if sid == self.id), self.nome)

    def posicao_do(self, id_: str) -> int:
        return self.episodios.index(self.episodio(id_)) + 1

    def rotulo_do(self, id_: str) -> str:
        """Como o episódio é identificado fora do site, no mesmo vocabulário da etiqueta: "Saga Software · ep. 2"."""
        return f"Saga {self.nome_curto} · ep. {self.posicao_do(id_)}"

    def referencias_do(self, episodio: Episodio) -> list[dict[str, Any]]:
        """Junta os dados de cada fonte em referencias_base com os capítulos pedidos pelo episódio."""
        base = {referencia["id"]: referencia for referencia in self.dados.get("referencias_base", [])}
        resolvidas = []
        for referencia in episodio.dados.get("referencias", []):
            fonte = referencia["fonte"]
            if fonte not in base:
                raise KeyError(f"Episódio {episodio.id} cita a fonte {fonte}, que não está em referencias_base.")
            resolvidas.append({**base[fonte], **{k: v for k, v in referencia.items() if k != "fonte"}})
        return resolvidas


def carregar_saga(arquivo: Path) -> Saga:
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    episodios = tuple(
        Episodio(
            id=item["id"],
            titulo=item["titulo"],
            pre_requisitos=tuple(item.get("pre_requisitos", [])),
            referencias_verificadas=bool(item.get("referencias_verificadas", False)),
            dados=item,
        )
        for item in dados.get("episodios", [])
    )
    return Saga(id=dados["id"], nome=dados["nome"], expert=dados["expert"], episodios=episodios, dados=dados)


def carregar_sagas(diretorio: Path) -> dict[str, Saga]:
    sagas = (carregar_saga(arquivo) for arquivo in sorted(diretorio.glob("*.yaml")))
    return {saga.id: saga for saga in sagas}
