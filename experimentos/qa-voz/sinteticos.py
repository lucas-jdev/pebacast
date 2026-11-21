"""Gera episódios com defeito no nível do áudio, a partir de episódios bons e da referência do Vosk.

Cada turno trocado mantém o intervalo e a duração originais: a fala de outra voz do Gemini, tirada
dos turnos de outra persona noutro episódio, é emendada e cortada para caber, com 20 ms de fade.
O resultado passa pelo mesmo caminho de um episódio publicado (MP3 a 64 kbps).

    sinteticos.py raiz audio saida destino
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from segmentacao import turnos_do_roteiro  # noqa: E402

# Na taxa do MP3 publicado (24 kHz): emendar e recodificar a 16 kHz cortava agudos e mudava o canal do
# episódio inteiro, o que a impressão de voz acusava como troca de voz até nos turnos intactos.
TAXA = 24_000
FADE = int(0.02 * TAXA)


def decodificar(mp3: Path) -> np.ndarray:
    saida = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(TAXA), "-f", "f32le", "-"],
                           check=True, capture_output=True).stdout
    return np.frombuffer(saida, dtype=np.float32).copy()

# (nome, episódio base, persona trocada, blocos trocados ou None para todos, (episódio doador, persona doadora))
DEFEITOS = [
    ("timbre-davi-por-rafael-bloco2", "sw-002", "davi", [2], ("si-002", "rafael")),
    ("timbre-davi-por-otavio-bloco1", "in-001", "davi", [1], ("co-001", "otavio")),
    ("timbre-helena-por-camila-bloco2", "sw-002", "helena", [2], ("da-001", "camila")),
    ("timbre-jorge-por-rafael-bloco1", "in-001", "jorge", [1], ("si-002", "rafael")),
    ("confusao-helena-vira-puck", "sw-002", "helena", None, ("sl-002", "davi")),
    ("confusao-jorge-vira-puck", "in-001", "jorge", None, ("co-001", "davi")),
    ("confusao-helena-vira-camila", "sw-002", "helena", None, ("da-001", "camila")),
    # Controle: o mesmo caminho de decodificar e recodificar, sem trocar nada. Não pode disparar.
    ("controle-sw-002", "sw-002", None, None, None),
    ("controle-in-001", "in-001", None, None, None),
]


def intervalos(saida: Path, ep: str) -> list[dict]:
    return json.loads((saida / f"{ep}.referencia.json").read_text(encoding="utf-8"))


def fala_da_persona(x: np.ndarray, ref: list[dict], persona: str) -> np.ndarray:
    pedacos = [x[int(t["inicio"] * TAXA):int(t["fim"] * TAXA)] for t in ref
               if t["persona"] == persona and t["inicio"] is not None and t["indice"] > 0]
    return np.concatenate(pedacos)


def encaixar(destino: np.ndarray, a: int, b: int, fonte: np.ndarray, cursor: int) -> int:
    n = b - a
    if cursor + n > len(fonte):
        cursor = 0
    pedaco = fonte[cursor:cursor + n].copy()
    rampa = np.linspace(0, 1, FADE)
    pedaco[:FADE] *= rampa
    pedaco[-FADE:] *= rampa[::-1]
    destino[a:b] = pedaco * (np.sqrt(np.mean(destino[a:b] ** 2)) / max(np.sqrt(np.mean(pedaco ** 2)), 1e-9))
    return cursor + n


def gerar(raiz: Path, audio: Path, saida: Path, destino: Path) -> None:
    for nome, base, persona, blocos, doador in DEFEITOS:
        x = decodificar(audio / f"pebacast-{base}.mp3")
        ref = intervalos(saida, base)
        bloco_do_turno = {t.indice: t.bloco for t in turnos_do_roteiro(raiz, base)}
        cursor, trocados = 0, 0
        if doador:
            fonte = fala_da_persona(decodificar(audio / f"pebacast-{doador[0]}.mp3"), intervalos(saida, doador[0]),
                                    doador[1])
        for t in ref if doador else []:
            if t["persona"] != persona or t["inicio"] is None or t["indice"] == 0:
                continue
            if blocos is not None and bloco_do_turno[t["indice"]] not in blocos:
                continue
            cursor = encaixar(x, int(t["inicio"] * TAXA), int(t["fim"] * TAXA), fonte, cursor)
            trocados += 1
        pasta = destino / nome
        pasta.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(TAXA), "-ac", "1", "-i", "-",
                        "-b:a", "64k", str(pasta / f"pebacast-{base}.mp3")], input=x.astype(np.float32).tobytes(),
                       check=True)
        (pasta / "defeito.json").write_text(json.dumps({"base": base, "persona": persona, "blocos": blocos,
                                                        "doador": doador,
                                                        "turnos_trocados": trocados}), encoding="utf-8")
        print(nome, "turnos trocados:", trocados)


if __name__ == "__main__":
    gerar(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
