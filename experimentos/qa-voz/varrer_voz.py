"""Varre o peso da evidência de voz na segmentação. Uso: varrer_voz.py raiz audio saida modelos modelo ep..."""

import copy
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avaliar_segmentacao import avaliar  # noqa: E402
from medir import Embedder  # noqa: E402
from segmentacao import decodificar, segmentar, turnos_do_roteiro  # noqa: E402

raiz, audio, saida, modelos, modelo = (Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                                       Path(sys.argv[4]), sys.argv[5])
episodios = sys.argv[6:]
embedder = Embedder(modelos, modelo)
dados = {ep: (decodificar(audio / f"pebacast-{ep}.mp3"), turnos_do_roteiro(raiz, ep),
              json.loads((saida / f"{ep}.referencia.json").read_text(encoding="utf-8"))) for ep in episodios}
for peso in (None, 0.05, 0.1, 0.3, 1.0):
    certos = total = 0
    linha = []
    for ep, (x, turnos, ref) in dados.items():
        comeco = time.perf_counter()
        t, info = segmentar(x, copy.deepcopy(turnos), embedder=embedder if peso else None, peso_voz=peso or 0)
        gasto = time.perf_counter() - comeco
        r = avaliar({"info": info, "turnos": [asdict(v) for v in t]}, ref)
        certos += r["persona_certa"]
        total += r["miolos"]
        linha.append(f"{ep} {r['taxa']:.3f} ({gasto:.0f}s)")
    print(f"peso_voz={peso} | total {certos}/{total} = {certos / total:.3f} | " + " | ".join(linha), flush=True)
