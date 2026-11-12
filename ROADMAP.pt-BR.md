# Roadmap

🌐 [English](ROADMAP.md) · **Português (BR)**

Estado do port nativo de Resistance 3 (`BCUS98176`) para macOS/arm64 e o que
vem a seguir. Mesmo formato dos roadmaps de Resistance: Fall of Man e
Resistance 2. `[x]` = feito e verificado; `[ ]` = a fazer; "(em andamento)" =
sendo trabalhado.

## Resumo (2026-11-11)

- **Inicia até a primeira tela.** O disco 01.00 foi decriptado, analisado,
  traduzido (35.741 funções) e compilado; o primeiro boot copia 1,5 GB para o
  HD e mostra uma tela a 30 fps que espera o X. Depois do X começa o vídeo de
  carregamento e o jogo para: os jobs do Bink nas filas 3 e 4 do sistema de
  jobs do igPm nunca terminam (próximo).

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
- [x] O disco (BCUS98176 01.00, hash do RPCS3 `PPU-502feb23…`): decriptado,
  analisado (3 ELFs SPU, 3 job modules, 18 blobs relocáveis; o `game.self` é
  o próprio EBOOT, então é um executável só), traduzido (35.741 funções) e
  compilado.
- [x] A tarefa de inflate do Edge zlib (o descompressor dos `.psarc`) é um ELF
  SPU sem seções cujo segmento de texto termina em dados: o gerador SPU do
  toolkit aceita `--text-end` por imagem (o `port/CMakeLists.txt` passa), e
  ela é traduzida.
- [x] Os dois policy modules SPURS crus traduzidos: Wws_Job
  (`tools/prepare_r3_job_pm.py`) e o igPm da Insomniac
  (`tools/prepare_r3_ig_pm.py`, novo desde o Resistance 2).
- [x] O igPm roda nas cinco SPUs da instância "ig", cada uma atendendo a fila
  de jobs cujo número o jogo escreve no seu SNR1. Toolkit: ids de thread SPU
  para as SPUs da SPURS no `cellSpursGetInfo` e `sys_spu_thread_write_snr`
  nelas; a tradução de um policy module não é usada depois que código é
  carregado por cima dele. Runner: `SPURS_WIDEN=0` e `SPU_CH_BLOCK=1` por
  padrão.
- [x] O `tools/rebuild.sh` compila uma parte por 10 GB de RAM, em prioridade
  baixa (o padrão do Ninja travou um Mac de 24 GB).
- [x] A cópia para o HD do primeiro boot (bancos de som, 1,5 GB, 5.218
  arquivos) e a primeira tela a 30 fps.

## Próximos

- [x] O vídeo de carregamento (jobs do igBink, traduzidos com
  `tools/lift_r3_igjobs.py`), o primeiro autosave, o lobby (menu) e,
  apertando X por ele, a primeira fase (`haven_town_ridge`) a 30 fps.
- [ ] Os módulos SPU relocáveis: 18 blobs DEADDEAD como no Resistance 2, e
  módulos com cabeçalho ila num formato mais novo (tabelas `igNav` e outras).
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
