# Roadmap

🌐 [English](ROADMAP.md) · **Português (BR)**

Estado do port nativo de Resistance 3 (`BCUS98176`) para macOS/arm64 e o que
vem a seguir. Mesmo formato dos roadmaps de Resistance: Fall of Man e
Resistance 2. `[x]` = feito e verificado; `[ ]` = a fazer; "(em andamento)" =
sendo trabalhado.

## Resumo (2026-11-11)

- **Montado, esperando o disco.** Os scripts, o patch do toolkit, o runner e
  o launcher estão no lugar e compilam; nada do Resistance 3 foi decriptado,
  traduzido ou iniciado ainda.

## Feito

- [x] Estrutura do repositório vinda do port do Resistance 2: `tools/`
  (instalação, rebuild, jogar, dependências sem Homebrew, decriptação sem
  RPCS3), `port/` (runner, patches, CMake), `launcher/`, docs nos dois
  idiomas, licença MIT.
- [x] O toolkit: ps3recomp v0.17.0 (`a6d76c8`) mais o patch do Resistance 2
  como `patches/ps3recomp-a6d76c8-resistance3.patch`; o
  `tools/setup_toolkit.sh` aplica e o `tools/export_toolkit_patch.sh` exporta
  de novo (ida e volta conferida).
- [x] `PS3_GAMEDATA_MARKERS` no `cellGame.c` do toolkit: os arquivos que
  marcam a instalação no HD da primeira vez como concluída eram os do
  Resistance 2, fixos no código.
- [x] O `port/CMakeLists.txt` configura e `main.cpp`, `patches.cpp`,
  `stubs.cpp` e o host da janela compilam contra o toolkit com patch
  (conferido com o lift do Resistance 2 no lugar); o `patches.cpp` recompila
  quando as palavras de patch geradas aparecem ou somem.
- [x] O launcher renomeado para o Resistance 3 (`BCUS98176`,
  `resistance-recomp-3`, `io.github.erikomis.resistance3recomp`): typecheck,
  build do frontend e os testes Rust (59) passam.
- [x] `tools/r3_survey.py`: o hash PPU do RPCS3 (conferido igual ao do RPCS3
  no EBOOT do Resistance 2) contra os quatro executáveis conhecidos do
  Resistance 3 (BCUS98176 / BCES01118, 01.00 / 01.05), PARAM.SFO, segmentos e
  seções, o TOC, ELFs SPU embutidos, job modules WWS, blobs relocáveis
  DEADDEAD, strings da Insomniac, outros executáveis e as palavras dos patches
  da comunidade (`--write-insn`: o `insn.json` do lift e as palavras do
  `patches.cpp`).
- [x] `tools/regen_r3_jobmods.sh`: o lift genérico dos job modules 0xC0DEC0DE.
- [x] "Unlock FPS" e "Extended FOV" do RPCS3 para 01.00 e 01.05 ligados no
  `port/patches.cpp` (`RES_UNLOCK_FPS`, `RES_FOV`), presos às palavras geradas
  a partir do EBOOT do jogador.

## Próximos

- [ ] Fazer o dump do disco; `tools/install.sh` (ou `tools/rebuild.sh toolkit
  decrypt survey`). Anotar a versão (01.00 ou 01.05) e a revisão da chave
  (`tools/decrypt_self.py --info`).
- [ ] Ler o survey: quantos ELFs SPU, job modules e blobs relocáveis; se há o
  loader `igInitRawSpu` e programas de raw SPU (Bink); se há um segundo
  executável (um exitspawn, como o `game.self` do Resistance 1).
- [ ] Analisar e traduzir o EBOOT; compilar e linkar tudo (o lift vai ser
  maior que as ~41.500 funções do Resistance 2).
- [ ] O código SPU cru, seguindo as ferramentas do Resistance 2: o policy
  module Wws_Job (`prepare_r2_job_pm.py`), o loader e os programas de raw SPU
  (`prepare_r2_rawspu_loader.py`, `prepare_r2_rawspu.py`), os módulos
  relocáveis (`lift_r2_relocmods.py`), como `tools/prepare_r3_*.py` e
  `tools/lift_r3_relocmods.py` com os endereços e fingerprints do Resistance 3.
- [ ] Primeiro boot: logos, o aviso de auto-save, input (o Resistance 2
  precisou de um hook de porta 0 no front-end), menus.
- [ ] A instalação no HD da primeira vez: quais arquivos o Resistance 3
  escreve, para o `PS3_GAMEDATA_MARKERS` e o `HDD_INSTALL_MARKERS` do
  launcher; os nomes dos slots de save para o gerenciador de saves.
- [ ] Vídeos (Bink num raw SPU no Resistance 2).
- [ ] New Game → a primeira fase; depois 30 fps do começo ao fim.
- [ ] `tools/r3_survey.py --write-insn` e `RES_UNLOCK_FPS=1` / `RES_FOV`
  jogando; depois 60 fps.
- [ ] Medir de novo o espaço em disco de uma instalação completa (o launcher
  e o `tools/install.sh` pedem 8 GB até lá).
- [ ] Publicar o repositório (`erikomis/resistance3-recomp`, o nome que o
  updater do launcher e o clone das fontes já usam) e a primeira release do
  launcher.

## Depois

- [ ] Multiplayer online. A Sony desligou os servidores do Resistance 3 junto
  com os do resto da série; os ports do Resistance 1 e 2 trazem a base no
  patch do toolkit (sockets reais `PS3_NET_ONLINE=1`, `PS3_NET_DNS`, um login
  PSN local `PS3_NP_SIGNIN=1`), tudo desligado por padrão e também neste
  patch. A campanha vem primeiro.
