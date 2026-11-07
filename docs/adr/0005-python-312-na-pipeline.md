# 0005. Python 3.12 na pipeline

- Status: Aceito
- Data: 2026-11-06

## Contexto

A pipeline é majoritariamente cola entre serviços: chama APIs de LLM e TTS, manipula YAML e JSON e invoca o ffmpeg. O fallback de voz (Kokoro) e a referência do teste (Piper) só existem como bibliotecas Python. O Kokoro 0.9.4 declara suporte a Python de 3.10 a 3.12.

A stack principal do autor é Java com Spring Boot.

## Decisão

Escrever a pipeline em Python 3.12, com dependências gerenciadas pelo uv. Os provedores de TTS ficam como dependências opcionais (`gemini`, `kokoro`, `piper`), e cada adaptador só importa a sua biblioteca quando é instanciado.

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Java com Spring Boot | Kokoro e Piper exigiriam rodar ONNX pela JVM ou chamar um processo Python, o que traz duas runtimes para o mesmo problema. Spring é pesado para um job batch de minutos |
| Python 3.13 | Incompatível com o Kokoro |
| Kokoro como serviço HTTP separado | Resolve a versão do Python, mas cria um serviço para manter, por causa de um fallback |

## Consequências

Positivas:

- Uma runtime só, e o ecossistema de áudio e IA mais completo.
- Com a importação tardia, quem usa só o Gemini não precisa instalar o PyTorch, que o Kokoro arrasta (cerca de 2 GB).

Negativas:

- A pipeline fica fora da stack principal do autor. Mitigado pelo tamanho pequeno do código e pelos testes automatizados.
- O Python fica preso em 3.12 até o Kokoro suportar 3.13.

## Critério de revisão

Revisar quando o Kokoro suportar Python 3.13 ou se o Kokoro deixar de ser o fallback.
