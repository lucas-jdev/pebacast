# Vinheta

A vinheta é um recorte de uma faixa musical de terceiros. Ela toca na abertura, por baixo da primeira fala, e de novo no encerramento.

## Faixa

| Campo | Valor |
|---|---|
| Faixa | indie rock, id 606263 na Pixabay. Título exato e autor: confirmar ao baixar |
| Origem | [Pixabay](https://pixabay.com/pt/music/rocha-indie-rock-606263/) |
| Licença | [Pixabay Content License](https://pixabay.com/pt/service/license-summary/) |

A licença da Pixabay permite usar a faixa num podcast, sem pagamento e sem atribuição obrigatória. Ela não permite distribuir a faixa sozinha. Por isso, o MP3 original nunca entra no repositório público: só a versão cifrada `assets/vinheta.mp3.gpg` é versionada, e o `.gitignore` bloqueia o resto da pasta `assets/`.

Pela mesma razão, a vinheta fica fora da CC BY 4.0 do conteúdo. Ver [LICENSE-CONTENT.md](../LICENSE-CONTENT.md).

## Como trocar a faixa ou o recorte

1. Baixe a faixa e salve em `assets/vinheta.mp3`.
2. Ajuste o recorte em `config/pipeline.yaml`, na chave `audio.vinheta`: início, duração, fades, sobreposição com a primeira fala, volume e se toca no encerramento.
3. Rode `scripts/cifrar_vinheta.sh`. Ele gera uma senha aleatória, cifra a faixa com AES-256, confere a decifragem e grava a senha no secret `VINHETA_SENHA`. A senha não aparece na tela nem fica salva no disco.
4. Commite `assets/vinheta.mp3.gpg` e a config.

## No GitHub Actions

O workflow `publicar.yml` decifra a faixa com o secret antes de montar o episódio. Se a decifragem falhar, por secret ausente ou senha errada, o episódio sai sem vinheta e uma issue de aviso é aberta. Um episódio não deixa de sair por causa da vinheta.
