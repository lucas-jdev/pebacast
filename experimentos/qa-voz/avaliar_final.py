"""Número final da segmentação: o modelo escolhido como evidência de voz, contra a referência do Vosk.

    avaliar_final.py raiz audio saida modelos modelo ep...
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avaliar_segmentacao import avaliar  # noqa: E402
from medir import Embedder  # noqa: E402
from segmentacao import decodificar, salvar, segmentar, turnos_do_roteiro  # noqa: E402

raiz, audio, saida, modelos, modelo = (Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                                       Path(sys.argv[4]), sys.argv[5])
embedder = Embedder(modelos, modelo)
certos = total = 0
resultado = {}
for ep in sys.argv[6:]:
    turnos, info = segmentar(decodificar(audio / f"pebacast-{ep}.mp3"), turnos_do_roteiro(raiz, ep), embedder=embedder)
    salvar(turnos, info, saida / f"{ep}.segmentos-final.json")
    ref = json.loads((saida / f"{ep}.referencia.json").read_text(encoding="utf-8"))
    r = avaliar({"info": info, "turnos": [asdict(t) for t in turnos]}, ref)
    certos += r["persona_certa"]
    total += r["miolos"]
    resultado[ep] = {k: v for k, v in r.items() if k != "errados"}
    print(ep, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in resultado[ep].items()}, flush=True)
print(f"TOTAL {certos}/{total} = {certos / total:.4f}")
(saida / f"segmentacao-final-{modelo}.json").write_text(json.dumps({"total": [certos, total], "episodios": resultado},
                                                                     indent=1), encoding="utf-8")
