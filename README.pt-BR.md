# Resistance 3 — recompilação estática para PC (macOS)

<a href="https://recomplauncher.com"><picture><source media="(prefers-color-scheme: dark)" srcset="https://recomplauncher.com/assets/press/launcher/badge-light.svg"><img alt="Get it on RecompLauncher" src="https://recomplauncher.com/assets/press/launcher/badge-dark.svg" height="48"></picture></a>

🌐 [English](README.md) · **Português (BR)**

Um port nativo de **Resistance 3** (PS3, disco `BCUS98176`; o disco europeu é
o `BCES01118`) para **macOS/arm64**, feito com recompilação estática: o código
PowerPC e SPU do jogo é traduzido para C/C++ e compilado num executável
nativo, com gráficos em Metal. Não é um emulador.

O terceiro port da série, depois dos ports do autor de
[Resistance: Fall of Man](https://github.com/erikomis/resistance-recomp) e
[Resistance 2](https://github.com/erikomis/resistance2-recomp), sobre o
[ps3recomp](https://github.com/sp00nznet/ps3recomp). O Resistance 3 é a mesma
engine da Insomniac três anos depois, então este port parte do patch do
toolkit, dos scripts, do runner e do launcher do port do Resistance 2. Veja
[CREDITS.pt-BR.md](CREDITS.pt-BR.md).

> [!WARNING]
> **Jogável no começo da campanha; não validado depois disso.** Instalação,
> menus, novo jogo, o porão e as ruas de Haven (incluindo a luta com o
> Stalker) rodam a 30 fps, o limite do jogo; os capítulos seguintes ainda não
> foram jogados. Até onde o jogo foi e o que vem a seguir estão no
> [ROADMAP.pt-BR.md](ROADMAP.pt-BR.md).
>
> **Este repositório não contém dados do jogo, firmware, chaves da Sony nem
> nada traduzido deles.** Cada um gera tudo isso localmente a partir da sua
> própria cópia legítima. Projeto de fã, sem vínculo com a Sony Interactive
> Entertainment ou a Insomniac Games.

## Estado

Em 2026-11-13: o disco 01.00 está traduzido e compilado. A instalação no HD,
os vídeos, os menus, Novo Jogo / Continuar, o porão e as ruas de Haven
funcionam, com colisão, menu de pausa e recarga de checkpoint; o combate em
Haven fica em 30 fps (mediana 30,0 fps, pior quadro ~60 ms), o código SPU roda
quase todo traduzido, e os pipelines são registrados e pré-montados a partir
de um arquivo binário, então as sessões seguintes não travam em shaders. A
campanha depois de Haven ainda não foi jogada. Detalhes no
[ROADMAP.pt-BR.md](ROADMAP.pt-BR.md).

- O toolkit: ps3recomp v0.17.0 (`a6d76c8`) mais
  `patches/ps3recomp-a6d76c8-resistance3.patch`, o patch do Resistance 2 com
  as adaptações de instalação, SPURS e código SPU do Resistance 3.
- `tools/r3_survey.py`, novo: identifica o EBOOT pelo hash PPU do RPCS3
  (01.00 do disco ou update 01.05, EUA ou Europa) e lista o que os ports
  anteriores tiveram que achar na mão: os ELFs SPU embutidos, os job modules
  WWS, os blobs SPU relocáveis, as peças da Insomniac citadas em strings
  (`igInitRawSpu`, `Wws_Job`, Bink), um eventual segundo executável e as
  palavras que os patches de FPS/FOV da comunidade mudam. Verificado no EBOOT
  do Resistance 2 (acha os 3 ELFs SPU, 29 job modules e 142 blobs relocáveis
  que aquele port documenta, e o hash do RPCS3 dele).
- Os patches da comunidade que o RPCS3 traz para este jogo ("Unlock FPS" de
  Whatcookie e boma, "Extended FOV" de illusion) estão ligados
  (`RES_UNLOCK_FPS`, `RES_FOV`), para serem gerados a partir do EBOOT.

## Como funciona

O mesmo caminho dos ports anteriores:

1. O `EBOOT.BIN` do disco (um SELF) é decriptado para ELF
   (`tools/decrypt_self.py`, com as chaves do código público do RPCS3; o
   próprio RPCS3 como alternativa).
2. O `ppu_loader.py` do toolkit acha as funções e os imports, e o
   `ppu_lifter.py` traduz cada função PowerPC para C++.
3. Os programas SPU são traduzidos para C: os ELFs SPU que o build acha
   sozinho, os job modules WWS (`tools/regen_r3_jobmods.sh`) e o código SPU
   cru que o survey apontar (`tools/prepare_r3_*.py` específicos do port,
   escritos à medida que forem encontrados).
4. O CMake compila isso com o runtime do toolkit (bibliotecas de firmware em
   HLE, syscalls lv2, SPURS, o backend RSX→Metal) e o `port/` (o runner, os
   patches) em `build/BCUS98176/ResistanceRecomp`.

## Compilando a partir do código

### O que é preciso

- Um Mac Apple Silicon (macOS com Metal).
- O seu próprio **disco de Resistance 3** (`BCUS98176`), em imagem montada ou
  extraído em `game/BCUS98176/` (a pasta que contém `PS3_GAME/`). Para o
  disco europeu, `RES_TITLE_ID=BCES01118`.
- As Command Line Tools do Xcode. O resto (CMake, Ninja, Python, SDL2,
  glslang, SPIRV-Cross, SPIRV-Tools, FFmpeg) o `tools/install.sh` instala sem
  Homebrew (`tools/bootstrap_deps.sh`), ou pelo Homebrew:

```sh
brew install cmake ninja sdl2 glslang spirv-cross spirv-tools ffmpeg python@3.12
```

### Compilando

```sh
git clone https://github.com/erikomis/resistance3-recomp.git
cd resistance3-recomp
tools/install.sh            # deps, toolkit, venv, decrypt, survey, analyse, lift, spu, build
```

ou, com as ferramentas já instaladas, `tools/rebuild.sh`, cujos passos também
rodam sozinhos pelo nome (`tools/rebuild.sh survey`, `tools/rebuild.sh lift build`):

| Passo | O que faz |
| --- | --- |
| `toolkit` | `tools/setup_toolkit.sh`: clona o ps3recomp em `./ps3recomp`, faz checkout de `a6d76c8`, aplica o patch |
| `decrypt` | `EBOOT.BIN` → `game/<title>/EBOOT.elf` (e o `PARAM.SFO` ao lado); `RES_EBOOT_BIN=<caminho>` decripta outro, por exemplo o do update 01.05 |
| `survey` | `tools/r3_survey.py` → `out/survey/<title>.txt` e `.json` |
| `analyse` | `ppu_loader.py` → `analysis/<title>/` |
| `lift` | `ppu_lifter.py` → `recompiled/<title>/` (24 partes; `JOBS` limita o paralelismo), com `port/patches/eboot_<versão>.insn.json` quando existe |
| `spu` | `tools/regen_r3_jobmods.sh` e cada `tools/prepare_r3_*.py` → `port/spu/` |
| `build` | CMake + Ninja → `build/<title>/ResistanceRecomp` e `build/<title>/Resistance` |

O disco é achado por `PS3_VFS_ROOT`, `game/<title>/PS3_GAME` ou um volume em
`/Volumes` cujo `PARAM.SFO` tenha o título (`tools/env.sh`).

### O update 01.05

Os patches da comunidade no RPCS3 existem para a 01.00 (o disco) e a 01.05 (o
último update). Para portar o executável do update, instale o update no
RPCS3 e aponte o passo de decrypt para o EBOOT dele:

```sh
rm -f game/BCUS98176/EBOOT.elf
RES_EBOOT_BIN=~/Library/Application\ Support/rpcs3/dev_hdd0/game/BCUS98176/USRDIR/EBOOT.BIN \
    tools/rebuild.sh decrypt survey analyse lift spu build
```

### Os patches de FPS e FOV

Depois de decriptar o EBOOT:

```sh
tools/r3_survey.py game/BCUS98176/EBOOT.elf --write-insn port/patches
tools/rebuild.sh lift build
```

gera `port/patches/eboot_<versão>.insn.json` (as palavras de código,
traduzidas nas duas formas) e `eboot_<versão>.words.h` (as palavras originais
que o `port/patches.cpp` confere, e as de dados que ele escreve). Aí
`RES_UNLOCK_FPS=1` e `RES_FOV=0.7` funcionam com o `tools/play.sh`.

## Jogando

O launcher em [`launcher/`](launcher/README.md) instala, recompila e joga sem
terminal (é o do port do Resistance 2, renomeado). Pelo terminal, com o disco
montado e um controle conectado:

```sh
tools/play.sh
```

Saves, as pastas do HD e o log (`last.log`) ficam em
`~/Library/Application Support/resistance-recomp-3/` (`RES_DATA`).

### Variáveis de ambiente

| Variável | Efeito |
| --- | --- |
| `RES_TITLE_ID` | `BCUS98176` (padrão) ou `BCES01118` |
| `PS3_VFS_ROOT` | a pasta que contém `PS3_GAME/` |
| `RES_EBOOT_BIN` | o `EBOOT.BIN` que o passo de decrypt lê |
| `RES_DATA` | saves, pastas do HD e o log |
| `RES_DEBUG=1` | diagnósticos de desenvolvimento (código SPU interpretado, policy modules da SPURS, chamadas de firmware mais frequentes, de onde o código SPU é carregado) e, ao sair, `logs/summary-<hora>.txt` com as linhas que importam |
| `RES_UNLOCK_FPS=1` | "Unlock FPS"; o FPS acompanha a taxa de vblank (`PS3_VBLANK_HZ`, padrão 62,5; o patch.yml desaconselha passar de 60–75) |
| `RES_FOV=<f>` | "Extended FOV" (o valor do RPCS3 é 0.7) |
| `RES_HTTP_POLL_COMPAT=0` | `cellHttpClientPollConnections` volta ao padrão do toolkit (vindo do Resistance 2, onde o padrão fazia a thread de HTTP girar sem parar) |
| `PS3_GAMEDATA_MARKERS` | os arquivos cuja presença indica que a instalação no HD da primeira vez terminou (separados por `:`, relativos à pasta de game data); o padrão é o par do Resistance 2 |

O runner mantém os padrões do Resistance 2 (escalonamento do SPURS no estilo
do kernel, eventos de `sys_lwcond`, RSX acordando a cada 50 µs, estéreo com
limitador); cada um tem uma chave para desligar e comparar, documentada no
`port/main.cpp` e no `tools/play.sh`.

## Atualizando o patch do toolkit

Mude o toolkit em `./ps3recomp` e rode:

```sh
tools/export_toolkit_patch.sh
```

que regenera `patches/ps3recomp-a6d76c8-resistance3.patch` a partir dele (sem
nunca exportar arquivos derivados do jogo) e confere que ele aplica num
`a6d76c8` limpo.

## Estrutura

| Caminho | O quê |
| --- | --- |
| `port/` | o runner (`main.cpp`), patches e hooks (`patches.cpp`, `stubs.cpp`), `CMakeLists.txt` |
| `port/patches/` | as palavras geradas dos patches de FPS/FOV (`tools/r3_survey.py --write-insn`) |
| `patches/` | o patch do toolkit |
| `tools/` | scripts de instalação, rebuild, jogo, survey, SPU e toolkit |
| `launcher/` | o app de desktop (Tauri) |
| `game/`, `analysis/`, `recompiled/`, `build/`, `out/`, `ps3recomp/` | gerados localmente, nunca vão para o git |

## Licença

MIT; veja [LICENSE](LICENSE) e [CREDITS.pt-BR.md](CREDITS.pt-BR.md).
