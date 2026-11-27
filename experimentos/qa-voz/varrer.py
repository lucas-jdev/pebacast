"""Varre os parâmetros da segmentação nos episódios de calibração (os de validação ficam de fora)."""

import copy
import itertools
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from avaliar_segmentacao import avaliar  # noqa: E402
from segmentacao import decodificar, segmentar, turnos_do_roteiro  # noqa: E402

raiz, audio, saida = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
episodios = sys.argv[4:]
dados = {ep: (decodificar(audio / f"pebacast-{ep}.mp3"), turnos_do_roteiro(raiz, ep),
              json.loads((saida / f"{ep}.referencia.json").read_text(encoding="utf-8"))) for ep in episodios}
for folga, peso, passadas in itertools.product((0, 12, 25), (0.3, 0.6, 1.2), (1, 2, 3)):
    linha = []
    for ep, (x, turnos, ref) in dados.items():
        t, info = segmentar(x, copy.deepcopy(turnos), folga, peso, passadas)
        r = avaliar({"info": info, "turnos": [asdict(v) for v in t]}, ref)
        linha.append(f"{ep} {r['taxa']:.3f} p90={r['erro_p90_s']:.1f}")
    print(f"folga={folga:>2} peso={peso} passadas={passadas} | " + " | ".join(linha))
