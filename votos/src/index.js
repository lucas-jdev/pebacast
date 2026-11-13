import { PedidoInvalido, identificarVisitante, lerPedido, placar, registrar } from "./votos.js";

const resposta = (status, corpo, cabecalhos = {}) =>
  new Response(corpo === null ? null : JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...cabecalhos },
  });

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname !== "/votos") return resposta(404, { erro: "não encontrado" });

    // O placar é público e vira insumo da pipeline; cache curto para não martelar o D1.
    if (request.method === "GET") {
      return resposta(200, await placar(env.DB), { "access-control-allow-origin": "*", "cache-control": "public, max-age=60" });
    }

    const cors = { "access-control-allow-origin": env.ORIGEM, vary: "Origin" };
    if (request.method !== "POST") return resposta(405, { erro: "método não permitido" }, { ...cors, allow: "GET, POST" });
    if (request.headers.get("origin") !== env.ORIGEM) return resposta(403, { erro: "origem não permitida" }, cors);
    if (!env.VOTOS_SAL) return resposta(503, { erro: "sal não configurado" }, cors);

    try {
      const pedido = lerPedido(await request.text());
      const visitante = await identificarVisitante(request.headers.get("cf-connecting-ip") ?? "", env.VOTOS_SAL);
      await registrar(env.DB, pedido, visitante, new Date().toISOString());
      return resposta(204, null, cors);
    } catch (erro) {
      if (erro instanceof PedidoInvalido) return resposta(400, { erro: erro.message }, cors);
      throw erro;
    }
  },
};
