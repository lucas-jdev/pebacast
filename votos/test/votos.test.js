import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";

import worker from "../src/index.js";
import { PedidoInvalido, identificarVisitante, lerPedido, lerRecado, placar, registrar } from "../src/votos.js";

const ORIGEM = "https://lucas-jdev.github.io";

// Mesma interface do D1 (prepare → bind → run/all), sobre o SQLite do Node, para testar o SQL de verdade.
function d1EmMemoria() {
  const db = new DatabaseSync(":memory:");
  for (const migracao of ["0001_votos.sql", "0002_recados.sql"]) {
    db.exec(readFileSync(new URL(`../migrations/${migracao}`, import.meta.url), "utf8"));
  }
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

const pedido = (corpo, { metodo = "POST", origem = ORIGEM, ip = "1.2.3.4", rota = "votos" } = {}) =>
  new Request(`https://api.test/${rota}`, {
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

const recado = (corpo, opcoes = {}) => pedido(corpo, { ...opcoes, rota: "recados" });

test("recado: aparado, com tamanho mínimo e máximo contados em caracteres", () => {
  assert.deepEqual(lerRecado('{"episodio":"si-001","texto":"  Muito bom!  "}'), { episodio: "si-001", texto: "Muito bom!", robo: false });
  assert.equal(lerRecado(JSON.stringify({ episodio: "si-001", texto: "🔥".repeat(1000) })).texto.length, 2000);
  for (const corpo of ['{"episodio":"si-001","texto":"  ok "}', JSON.stringify({ episodio: "si-001", texto: "a".repeat(1001) }),
    '{"episodio":"si-001","texto":5}', '{"episodio":"x","texto":"Muito bom"}']) {
    assert.throws(() => lerRecado(corpo), PedidoInvalido, corpo);
  }
});

test("recado do site é guardado e não existe rota pública para lê-lo", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: "Explica melhor o CAP?" }), env)).status, 204);
  assert.equal((await worker.fetch(pedido(null, { metodo: "GET", rota: "recados" }), env)).status, 405);
  const { results } = await env.DB.prepare("SELECT episodio, texto FROM recados").all();
  assert.deepEqual(results.map((r) => ({ ...r })), [{ episodio: "si-001", texto: "Explica melhor o CAP?" }]);
});

test("robô que preenche o campo invisível recebe 204 e nada é guardado", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: "compre já", site: "http://spam" }), env)).status, 204);
  assert.equal((await env.DB.prepare("SELECT COUNT(*) AS n FROM recados").all()).results[0].n, 0);
});

test("no máximo 5 recados por visitante por dia; outro IP não é afetado", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  for (let i = 0; i < 5; i++) assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: `recado ${i}` }), env)).status, 204);
  assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: "mais um" }), env)).status, 429);
  assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: "de outra rede" }, { ip: "5.6.7.8" }), env)).status, 204);
});

test("recado de outra origem é recusado", async () => {
  const env = { DB: d1EmMemoria(), ORIGEM, VOTOS_SAL: "sal" };
  assert.equal((await worker.fetch(recado({ episodio: "si-001", texto: "oi oi" }, { origem: "https://mal.example" }), env)).status, 403);
});
