from podcast.site import gerar_index
from tests.test_publicacao import _publicar
from tests.test_roteiro import _escrever_episodio, projeto  # noqa: F401 (fixture)


def test_pagina_mostra_episodio_publicado_com_player_e_desafio(projeto, tmp_path):
    noticia = {"tipo": "noticia", "titulo": "Apagão <ao vivo>", "url": "https://n/1", "fonte": "Jornal",
               "data": "2026-11-01", "nota_relevancia": 8, "justificativa": "j"}
    _escrever_episodio(projeto, "sw-001", noticia=noticia)
    _publicar(projeto, tmp_path)

    pagina = gerar_index(projeto, "feed.xml")

    assert 'id="sw-001"' in pagina
    assert "Liste dois trade-offs." in pagina
    assert '<audio controls preload="none" src="' in pagina
    assert "Apagão &lt;ao vivo&gt;" in pagina
    assert "feed.xml" in pagina


def test_pagina_sem_episodios_convida_a_assinar(projeto):
    pagina = gerar_index(projeto, "feed.xml")

    assert "<audio" not in pagina
    assert "O primeiro episódio está sendo cavado." in pagina
