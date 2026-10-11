# MiniNovers: anonimização de documentos (RGPD)

Ferramenta que deteta dados pessoais e sensíveis num documento e os oculta,
trocando **cada palavra sensível por um `*`** sem mudar mais nada, e explica
num relatório o que ocultou e porquê. Feita no NOS Gen-AI Hackathon.

Funciona com qualquer tipo de documento, não só o do desafio (um relatório de
admissão hospitalar fictício). O utilizador revê o resultado e **aprova ou
rejeita**, e pode escrever instruções do tipo "mascara também o nome da
clínica" ou "não mascares a informação médica".

## O que faz

| Entrada | O que sai |
|---|---|
| Texto e PDF | o texto com `*`, o PDF anonimizado e um relatório |
| Áudio | o áudio com cada palavra sensível trocada por um som |
| Fotografia | a imagem com as zonas sensíveis desfocadas |
| Vídeo | o vídeo com as zonas sensíveis desfocadas (só a imagem, não o som) |

Tudo se revê numa interface web, que também deixa escolher entre seis temas de
cor e o modo claro ou escuro.

## Como funciona

```
Documento -> Gemini deteta + regras de segurança -> o código mascara
          -> verificação -> resultado + relatório -> revisão na UI
```

- **O modelo deteta, o código mascara.** O Gemini só devolve a lista do que é
  sensível; quem escreve os `*` é o código, por isso a formatação nunca
  depende do modelo.
- **Regras de segurança** (NIF, email, telefone, cartão...) apanham o que o
  modelo falhe e correm sem ele.
- **As chaves não vão para o browser.** Um Worker da Cloudflare guarda as
  chaves do Gemini e do ElevenLabs e deixa qualquer pessoa usar a ferramenta
  sem ter uma.
- O critério do prompt é a **reidentificação**: é sensível o que, sozinho ou
  com o resto do documento, pode identificar uma pessoa ou revelar
  informação sensível sobre ela.
