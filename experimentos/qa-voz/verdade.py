"""Referência para conferir a segmentação: reconhecimento de fala (Vosk, pt) alinhado ao roteiro.

Só serve ao spike. O Vosk dá o tempo de cada palavra que reconheceu; um alinhamento de sequência
casa essas palavras com as do roteiro, e o intervalo de cada turno vai da primeira à última palavra
dele que casou. Turno sem palavra casada fica sem referência e não entra na conta.
"""

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from segmentacao import TAXA, decodificar  # noqa: E402


def normalizar(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", sem_acento)


def reconhecer(x: np.ndarray, modelo: Path) -> list[dict]:
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    rec = KaldiRecognizer(Model(str(modelo)), TAXA)
    rec.SetWords(True)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()
    palavras = []
    for i in range(0, len(pcm), 32000):
        if rec.AcceptWaveform(pcm[i:i + 32000]):
            palavras += json.loads(rec.Result()).get("result", [])
    palavras += json.loads(rec.FinalResult()).get("result", [])
    return palavras


def referencia(raiz: Path, episodio: str, palavras: list[dict]) -> list[dict]:
    from segmentacao import turnos_do_roteiro  # noqa: F401 (garante o sys.path do projeto)

    sys.path.insert(0, str(raiz / "src"))
    from podcast.personas import carregar_personas
    from podcast.publicacao import falas_do_episodio
    from podcast.roteiro import Projeto

    projeto = Projeto(raiz)
    falas = falas_do_episodio(projeto.episodios / episodio, carregar_personas(raiz / "curriculum" / "personas"),
                              projeto.config()["tts"])
    tokens, dono = [], []
    for indice, fala in enumerate(falas):
        for token in normalizar(fala.texto):
            tokens.append(token)
            dono.append(indice)
    ouvidas = [normalizar(p["word"])[0] if normalizar(p["word"]) else "" for p in palavras]
    casamento = difflib.SequenceMatcher(None, tokens, ouvidas, autojunk=False)
    tempos: dict[int, list[tuple[float, float]]] = {}
    for bloco in casamento.get_matching_blocks():
        for k in range(bloco.size):
            p = palavras[bloco.b + k]
            tempos.setdefault(dono[bloco.a + k], []).append((p["start"], p["end"]))
    saida = []
    for indice, fala in enumerate(falas):
        casadas = tempos.get(indice, [])
        total = len(normalizar(fala.texto))
        saida.append({
            "indice": indice, "persona": fala.persona.id, "palavras": total, "casadas": len(casadas),
            "inicio": min(a for a, _ in casadas) if casadas else None,
            "fim": max(b for _, b in casadas) if casadas else None,
        })
    return saida


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("raiz", type=Path)
    p.add_argument("audio", type=Path)
    p.add_argument("modelo", type=Path)
    p.add_argument("saida", type=Path)
    p.add_argument("episodios", nargs="+")
    a = p.parse_args()
    for ep in a.episodios:
        palavras = reconhecer(decodificar(a.audio / f"pebacast-{ep}.mp3"), a.modelo)
        ref = referencia(a.raiz, ep, palavras)
        (a.saida / f"{ep}.palavras.json").write_text(json.dumps(palavras), encoding="utf-8")
        (a.saida / f"{ep}.referencia.json").write_text(json.dumps(ref, indent=1), encoding="utf-8")
        casadas = sum(t["casadas"] for t in ref)
        total = sum(t["palavras"] for t in ref)
        print(ep, f"{len(palavras)} palavras ouvidas, {casadas}/{total} do roteiro casadas",
              f"({casadas / total:.0%}); turnos sem referência: {sum(t['casadas'] == 0 for t in ref)}")
