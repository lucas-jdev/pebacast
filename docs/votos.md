# Votos (curti / não curti)

Decisão e motivos: [ADR 0007](adr/0007-votos-worker-d1.md). Código: `votos/`. Deploy: `.github/workflows/votos.yml`.

## Ligar pela primeira vez

1. Crie uma conta gratuita na Cloudflare.
2. Em **My Profile → API Tokens → Create Token**, use o modelo **Edit Cloudflare Workers** e adicione a permissão **Account → D1 → Edit**.
3. No repositório, em **Settings → Secrets and variables → Actions**, crie os secrets:
   - `CLOUDFLARE_API_TOKEN`: o token do passo 2;
   - `CLOUDFLARE_ACCOUNT_ID`: o Account ID que aparece na lateral do painel da Cloudflare.
4. Rode o workflow **Votos** (Actions → Votos → Run workflow). Ele cria o banco, aplica a migração, publica o Worker e gera o sal. A URL do Worker aparece no log do passo "Publicar o Worker", no formato `https://pebacast-votos.<subdominio>.workers.dev`.
5. Coloque essa URL em `site.votos_api`, no `config/pipeline.yaml`, e faça o push. O site passa a mostrar os botões.

## Ler o placar

```
curl https://pebacast-votos.<subdominio>.workers.dev/votos
{"si-001": {"curti": 3, "nao_curti": 1}}
```

## Testes

```
cd votos && node --test
```

Os testes rodam o SQL de verdade no SQLite do Node (`node:sqlite`), pela mesma interface do D1.
