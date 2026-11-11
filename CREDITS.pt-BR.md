# Créditos

🌐 [English](CREDITS.md) · **Português (BR)**

Este port só existe por causa do trabalho abaixo. Obrigado a todos.

## Toolkit

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)** — Ned Heller
  ([@sp00nznet](https://github.com/sp00nznet)) e
  [colaboradores](https://github.com/sp00nznet/ps3recomp/blob/master/CONTRIBUTORS.md).
  O runtime, as bibliotecas HLE, os tradutores de PPU e SPU, o backend Metal, o
  cellVdec com FFmpeg e o template de projeto de onde partem o `main.cpp`, o
  `stubs.cpp`, o `CMakeLists.txt` e o `config.toml` deste port. O port compila
  contra a v0.17.0 (`a6d76c8`). MIT.

## Correções do toolkit vindas de pull requests do upstream

O patch do toolkit (o do Resistance: Fall of Man, dentro do do Resistance 2
de onde o patch deste port parte) traz estes pull requests do ps3recomp (alguns adaptados à v0.17.0 ou
àquele port), com os autores mantidos nos cabeçalhos do patch:

- **undecuple** — a área de licença do console, América do Norte (corrigiu o
  texto sobreposto das telas legais; [#429](https://github.com/sp00nznet/ps3recomp/pull/429)); XInput carregado em tempo de
  execução no Windows ([#494](https://github.com/sp00nznet/ps3recomp/pull/494)).
- **n0madic** ([@n0madic](https://github.com/n0madic)) — os bits de desvio dos
  vertex programs ([#485](https://github.com/sp00nznet/ps3recomp/pull/485)); `WPOS` em render targets com antisserrilhamento
  ([#446](https://github.com/sp00nznet/ps3recomp/pull/446)).
- **Will Tekulve** ([@tekulvw](https://github.com/tekulvw)) — a condição de
  corrida da tabela de fds ([#430](https://github.com/sp00nznet/ps3recomp/pull/430)); decodificação rápida de A8R8G8B8 linear
  ([#432](https://github.com/sp00nznet/ps3recomp/pull/432)); a memória dos slots de textura ([#438](https://github.com/sp00nznet/ps3recomp/pull/438)); o decrementador da
  SPU no relógio bruto ([#451](https://github.com/sp00nznet/ps3recomp/pull/451)); ceder a vez em DMA de SPU repetido
  ([#448](https://github.com/sp00nznet/ps3recomp/pull/448)); pequenas economias de DMA de SPU ([#453](https://github.com/sp00nznet/ps3recomp/pull/453), [#454](https://github.com/sp00nznet/ps3recomp/pull/454), [#455](https://github.com/sp00nznet/ps3recomp/pull/455)).
- **Heitor Mendonça** — reposicionar o arquivo quando o fd alterna entre
  leitura e escrita ([#456](https://github.com/sp00nznet/ps3recomp/pull/456)).
- **Ryan Bagas** — a nova checagem da reserva no `stwcx.` ([#522](https://github.com/sp00nznet/ps3recomp/pull/522)).
- **Noah Peterson** ([@NoahBPeterson](https://github.com/NoahBPeterson)) — o
  ritmo em tempo real do mixer de áudio POSIX (do trabalho no inFAMOUS 2).
- **erikomis** — `getenv` consultado uma vez por ponto de chamada ([#515](https://github.com/sp00nznet/ps3recomp/pull/515));
  volume e saída de áudio; o giro opcional do `usleep`.

As mudanças do Resistance 2 acrescentam:

- **Ryan Setyanto** ([@rigaz29](https://github.com/rigaz29)) — os primeiros
  128 bytes de um PUT do SPU escritos por último ([#632](https://github.com/sp00nznet/ps3recomp/pull/632), portado).

## Os ports que servem de modelo

- **[resistance2-recomp](https://github.com/erikomis/resistance2-recomp)** —
  o port do Resistance 2 do mesmo autor. Este repositório começa como uma
  cópia dele: o patch do toolkit, o `tools/` (instalação, rebuild, jogar,
  dependências, decriptação, o lift dos módulos de job), o runner em `port/`,
  o launcher, e o trabalho com raw SPU, módulo de política e módulos
  relocáveis que o Resistance 3 vai seguir.
- **[resistance-recomp](https://github.com/erikomis/resistance-recomp)** — o
  port do Resistance: Fall of Man do mesmo autor, sobre o mesmo toolkit. O
  patch de toolkit dele é a base do do Resistance 2, e de lá vêm a organização do
  repositório, a abordagem de patch do toolkit (`tools/setup_toolkit.sh`), os
  scripts de compilação e de jogo, o launcher da janela, as ferramentas dos
  módulos de job de SPU (`tools/extract_jobmods_elf.py`) e o trabalho com raw
  SPU e módulo de política.
- **[infamous2-recomp](https://github.com/erikomis/infamous2-recomp)** — o
  port do inFAMOUS 2 do mesmo autor, onde começaram essa organização, a
  extração dos módulos de job e a correção de rodar o guest fora da thread
  principal do macOS. Ele, por sua vez, se apoia no fork do inFAMOUS 1 do
  ps3recomp feito por [NoahBPeterson](https://github.com/NoahBPeterson/ps3recomp).

## Patches da comunidade

- As entradas do `patch.yml` do RPCS3 para o Resistance 3: **Whatcookie** e
  **boma** ("Unlock FPS") e **illusion** ("Extended FOV"), trazidas pelo
  `port/patches.cpp` e pelo `tools/r3_survey.py`.

## Ferramentas

- [RPCS3](https://github.com/RPCS3/rpcs3) — a tabela pública de chaves
  (`tools/fetch_keys.py`) e o `rpcs3 --decrypt` para o `EBOOT.BIN` do próprio
  jogador, o hash PPU pelo qual os patches dele são identificados, e a
  referência de comportamento do toolkit.
- [FFmpeg](https://ffmpeg.org/) (libavcodec, libavutil; LGPL/GPL, carregado em
  runtime a partir da instalação do Homebrew do próprio jogador, não
  distribuído aqui) — decodificação de vídeo.
- [SDL2](https://www.libsdl.org/), [glslang](https://github.com/KhronosGroup/glslang),
  [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross),
  [SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools), CMake, Ninja.
- [SMAA](https://github.com/iryoku/smaa) — Jorge Jimenez, Jose I. Echevarria,
  Belen Masia, Fernando Navarro e Diego Gutierrez: o antisserrilhamento do
  `PS3_AA=smaa` (`third_party/smaa` no patch do toolkit, com o arquivo de
  licença). MIT.
- A [PS3 Developer Wiki](https://www.psdevwiki.com/ps3/).

## Jogo

Resistance 3 © 2011 Sony Interactive Entertainment LLC, desenvolvido pela
Insomniac Games. Este projeto não é afiliado nem endossado pela Sony ou pela
Insomniac, e não contém dados do jogo nem do firmware. Para usá-lo você
precisa de uma cópia legítima do jogo (o disco `BCUS98176` ou `BCES01118`).
