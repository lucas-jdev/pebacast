-- Um voto por visitante e episódio; votar de novo troca o voto, desmarcar apaga.
CREATE TABLE votos (
  episodio TEXT NOT NULL,
  visitante TEXT NOT NULL,
  voto INTEGER NOT NULL CHECK (voto IN (-1, 1)),
  atualizado_em TEXT NOT NULL,
  PRIMARY KEY (episodio, visitante)
) WITHOUT ROWID;
