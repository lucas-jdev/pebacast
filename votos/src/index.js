import {
  PedidoInvalido,
  RECADO,
  guardarRecado,
  identificarVisitante,
  lerPedido,
  lerRecado,
  placar,
  recadosNoUltimoDia,
  registrar,
} from "./votos.js";

const resposta = (status, corpo, cabecalhos = {}) =>
  new Response(corpo === null ? null : JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...cabecalhos },
  });

const corsDoSite = (env) => ({ "access-control-allow-origin": env.ORIGEM, vary: "Origin" });

function recusarForaDoSite(request, env) {
  const cors = corsDoSite(env);
  if (request.method !== "POST") return resposta(405, { erro: "método não permitido" }, { ...cors, allow: "POST" });
  if (request.headers.get("origin") !== env.ORIGEM) return resposta(403, { erro: "origem não permitida" }, cors);
  if (!env.VOTOS_SAL) return resposta(503, { erro: "sal não configurado" }, cors);
  return null;
}

async function receberRecado(request, env) {
  const recusa = recusarForaDoSite(request, env);
  if (recusa) return recusa;
  const cors = corsDoSite(env);
  try {
    const recado = lerRecado(await request.text());
    if (recado.robo) return resposta(204, null, cors);
    const visitante = await identificarVisitante(request.headers.get("cf-connecting-ip") ?? "", env.VOTOS_SAL);
    const agora = new Date().toISOString();
    if ((await recadosNoUltimoDia(env.DB, visitante, agora)) >= RECADO.porDia) {
      return resposta(429, { erro: "limite de recados por dia" }, cors);
    }
    await guardarRecado(env.DB, recado, visitante, agora);
    return resposta(204, null, cors);
  } catch (erro) {
    if (erro instanceof PedidoInvalido) return resposta(400, { erro: erro.message }, cors);
    throw erro;
  }
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === "/recados") return receberRecado(request, env);
    if (pathname !== "/votos") return resposta(404, { erro: "não encontrado" });

    // O placar é público e vira insumo da pipeline; cache curto para não martelar o D1.
    if (request.method === "GET") {
      return resposta(200, await placar(env.DB), { "access-control-allow-origin": "*", "cache-control": "public, max-age=60" });
    }

    const recusa = recusarForaDoSite(request, env);
    if (recusa) return recusa;
    const cors = corsDoSite(env);

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
