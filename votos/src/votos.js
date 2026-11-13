export const VOTOS = { curti: 1, nao_curti: -1 };
const EPISODIO = /^[a-z]{2}-\d{3}$/;
const MAX_CORPO = 200;

export class PedidoInvalido extends Error {}

export function lerPedido(texto) {
  if (texto.length > MAX_CORPO) throw new PedidoInvalido("corpo grande demais");
  let dados;
  try {
    dados = JSON.parse(texto);
  } catch {
    throw new PedidoInvalido("JSON inválido");
  }
  const { episodio, voto } = dados ?? {};
  if (typeof episodio !== "string" || !EPISODIO.test(episodio)) throw new PedidoInvalido("episódio inválido");
  if (voto !== null && !Object.hasOwn(VOTOS, voto)) throw new PedidoInvalido("voto inválido");
  return { episodio, valor: voto === null ? null : VOTOS[voto] };
}

// O IP nunca é gravado: só um HMAC dele, que sem o sal não volta a ser IP.
export async function identificarVisitante(ip, sal) {
  const chave = await crypto.subtle.importKey("raw", new TextEncoder().encode(sal), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const assinatura = await crypto.subtle.sign("HMAC", chave, new TextEncoder().encode(ip));
  return [...new Uint8Array(assinatura)].slice(0, 16).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function registrar(db, { episodio, valor }, visitante, agora) {
  if (valor === null) {
    await db.prepare("DELETE FROM votos WHERE episodio = ?1 AND visitante = ?2").bind(episodio, visitante).run();
    return;
  }
  await db
    .prepare(
      `INSERT INTO votos (episodio, visitante, voto, atualizado_em) VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT (episodio, visitante) DO UPDATE SET voto = excluded.voto, atualizado_em = excluded.atualizado_em`,
    )
    .bind(episodio, visitante, valor, agora)
    .run();
}

export async function placar(db) {
  const { results } = await db
    .prepare(
      `SELECT episodio, SUM(voto = 1) AS curti, SUM(voto = -1) AS nao_curti
       FROM votos GROUP BY episodio ORDER BY episodio`,
    )
    .all();
  return Object.fromEntries(results.map(({ episodio, curti, nao_curti }) => [episodio, { curti, nao_curti }]));
}
