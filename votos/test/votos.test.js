import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";

import worker from "../src/index.js";
import { PedidoInvalido, identificarVisitante, lerPedido, placar, registrar } from "../src/votos.js";

const ORIGEM = "https://lucas-jdev.github.io";

// Mesma interface do D1 (prepare → bind → run/all), sobre o SQLite do Node, para testar o SQL de verdade.
function d1EmMemoria() {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../migrations/0001_votos.sql", import.meta.url), "utf8"));
  return {
    prepare: (sql) => ({
      bind: (...args) => ({
        run: async () => db.prepare(sql).run(...args),
        all: async () => ({ results: db.prepare(sql).all(...args) }),
      }),
      all: async () => ({ results: db.prepare(sql).all() }),
    }),
  };
}

const pedido = (corpo, { metodo = "POST", origem = ORIGEM, ip = "1.2.3.4" } = {}) =>
  new Request("https://api.test/votos", {
    method: metodo,
    headers: { origin: origem, "cf-connecting-ip": ip, "content-type": "text/plain" },
    body: metodo === "POST" ? JSON.stringify(corpo) : undefined,
  });

test("lê voto, troca e desmarcação", () => {
  assert.deepEqual(lerPedido('{"episodio":"si-001","voto":"curti"}'), { episodio: "si-001", valor: 1 });
  assert.deepEqual(lerPedido('{"episodio":"si-001","voto":"nao_curti"}'), { episodio: "si-001", valor: -1 });
  assert.deepEqual(lerPedido('{"episodio":"si-001","voto":null}'), { episodio: "si-001", valor: null });
});

test("recusa episódio, voto e corpo fora do formato", () => {
  for (const corpo of ['{"episodio":"../x","voto":"curti"}', '{"episodio":"si-001","voto":"amei"}',
    '{"episodio":"si-001","voto":"toString"}', "não é json", "x".repeat(201)]) {
    assert.throws(() => lerPedido(corpo), PedidoInvalido, corpo);
  }
});

test("visitante é um hash estável que não expõe o IP", async () => {
  const a = await identificarVisitante("1.2.3.4", "sal");
  assert.equal(a, await identificarVisitante("1.2.3.4", "sal"));
  assert.notEqual(a, await identificarVisitante("1.2.3.4", "outro-sal"));
  assert.match(a, /^[0-9a-f]{32}$/);
});

test("um voto por visitante: votar de novo troca, desmarcar apaga", async () => {
  const db = d1EmMemoria();
  await registrar(db, { episodio: "si-001", valor: 1 }, "a", "t1");
  await registrar(db, { episodio: "si-001", valor: 1 }, "b", "t1");
  await registrar(db, { episodio: "si-001", valor: -1 }, "a", "t2");
  await registrar(db, { episodio: "sl-001", valor: 1 }, "a", "t2");
  await registrar(db, { episodio: "sl-001", valor: null }, "a", "t3");

  assert.deepEqual(await placar(db), { "si-001": { curti: 1, nao_curti: 1 } });
});

test("POST do site grava e responde 204 com CORS só para a origem do site", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  const res = await worker.fetch(pedido({ episodio: "si-001", voto: "curti" }), env);
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("access-control-allow-origin"), ORIGEM);

  const get = await worker.fetch(pedido(null, { metodo: "GET" }), env);
  assert.deepEqual(await get.json(), { "si-001": { curti: 1, nao_curti: 0 } });
});

test("POST de outra origem é recusado", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  const res = await worker.fetch(pedido({ episodio: "si-001", voto: "curti" }, { origem: "https://mal.example" }), env);
  assert.equal(res.status, 403);
  assert.deepEqual(await placar(env.DB), {});
});

test("pedido inválido vira 400 e sem sal configurado vira 503", async () => {
  const db = d1EmMemoria();
  assert.equal((await worker.fetch(pedido({ episodio: "x", voto: "curti" }), { DB: db, ORIGEM, VOTOS_SAL: "s" })).status, 400);
  assert.equal((await worker.fetch(pedido({ episodio: "si-001", voto: "curti" }), { DB: db, ORIGEM })).status, 503);
});
