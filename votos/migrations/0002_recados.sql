-- Recado opcional que acompanha o voto. Privado: não há rota pública de leitura.
CREATE TABLE recados (
  id INTEGER PRIMARY KEY,
  episodio TEXT NOT NULL,
  visitante TEXT NOT NULL,
  texto TEXT NOT NULL CHECK (length(texto) BETWEEN 3 AND 1000),
  criado_em TEXT NOT NULL
);
CREATE INDEX recados_por_visitante ON recados (visitante, criado_em);
