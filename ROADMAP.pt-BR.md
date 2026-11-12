# Roadmap

🌐 [English](ROADMAP.md) · **Português (BR)**

Estado do port nativo de Resistance 3 (`BCUS98176`) para macOS/arm64 e o que
vem a seguir. Mesmo formato dos roadmaps de Resistance: Fall of Man e
Resistance 2. `[x]` = feito e verificado; `[ ]` = a fazer; "(em andamento)" =
sendo trabalhado.

## Resumo (2026-11-12)

- **Inicia, reproduz vídeos, abre o menu e joga a primeira fase.** O disco
  01.00 está traduzido e compilado, e o personagem anda no chão: as sondas de
  chão retornam acertos (4 a 18 por consulta) e a câmera fica na altura do
  piso.
- A gameplay fica em ~29 fps em média mesmo com o Mac em throttling térmico
  (eram 18-20 nesse estado): o laço de jobs do igPm agora é traduzido
  (`lift_r3_igjobs.py --loop`, já no `tools/rebuild.sh`); interpretado, ele
  zerava o bss de cada job uma quadword por vez, ~20 M passos interpretados
  por segundo. E uma thread que só lê o timebase (a thread principal
  esperando os jobs SPU) dorme 10 us por leitura depois de 2000 leituras
  vazias, em vez de segurar um núcleo a 100% (`PS3_TB_POLL_SLEEP_US`,
  0 = desligado).
- Ruas de Haven: o cache de texturas do motor RSX guarda 4096 texturas
  (`PS3RECOMP_ENG_TEXCACHE_SLOTS`, padrão do port; eram 1024). Com 1024 ele
  expulsava e reenviava ~9.500 texturas a cada 120 quadros nas áreas
  abertas (quadros de 300-800 ms, 6 fps), e expulsar no meio de um quadro é
  o que deixava o fundo do menu de pausa em faixas verticais. Linhas, line
  strips e line loops são reconstruídos numa lista de linhas que respeita os
  cortes de restart (`PS3RECOMP_ENG_LINE_REBUILD`, ligado): os fios de luz,
  line strips indexados, ligavam cada fio ao próximo atravessando o céu.
- Gameplay no limite de 30 fps no combate em Haven (mediana 29,9 fps; o tempo
  de CPU da thread do RSX por quadro foi de 44 para 22 ms ao longo do dia): o
  motor RSX deixa de manter o estado "shadow" legado que ninguém lê, acha
  texturas por um índice de hash, copia só as constantes de vértice que
  mudaram, entrega listas de triângulos remapeadas ao Metal como índices, e
  mais (chaves: `GCM_STATE_SHADOW`, `PS3RECOMP_ENG_TEXSLOT_INDEX`,
  `PS3RECOMP_ENG_VSCB_SYNC`, `PS3RECOMP_ENG_ADDR_FILTER`). A/B na mesma luta:
  22,9 fps com elas desligadas.
- Código SPU interpretado na gameplay caiu de ~2,5 M para ~0,0-0,1 M passos/s:
  o runtime mantém 16 regiões residentes com troca pela usada há mais tempo
  (o submódulo de física 0x00DB2D80 perdia a vaga para regiões velhas),
  confere que a região ainda contém o código antes de entrar nela, e rotinas
  que um job WWS só chama por tabela de ponteiros ganharam entradas
  traduzidas. `SPU_RESIDENT_POLICY=old`, `SPU_RESIDENT_VERIFY=0`,
  `SPU_RESIDENT_SLOTS`, `SPU_NO_ENTRY` para A/B.
- Fundo do menu de pausa: o jogo guarda o quadro congelado na memória do
  depth buffer de meia resolução; o motor aposentava esse alvo à toa,
  reaproveitava a vaga morta como viva e restaurava a partir do depth
  (profundidade pintada como cor). Corrigido no motor.
- Trava intermitente na gameplay (a thread principal chamando um método
  virtual por uma tabela zerada ~50 s depois do início da fase): o leitor da
  FIFO do GCM seguia uma lista de comandos temporária que o jogo libera logo
  depois de o RSX voltar dela, lia os bytes liberados como estado NV4097,
  associava um render target lixo e o motor o gravava sem checar limites,
  caindo no .bss do jogo. O leitor agora guarda o JUMP de volta do desvio
  (`GCM_DETOUR_RETURN`), gravações fora da memória do RSX são recusadas
  (`PS3RECOMP_ENG_STORE_BOUNDS`) e um alarme registra "FIFO desync suspect".
  Um caso de desalinhamento ainda ocorre (contido).
- Cunhas translúcidas verdes e escuras indo até o céu (fitas e billboards
  perto de efeitos e do Stalker): arrays de vértices do RSX com stride 0 eram
  lidos como arrays compactados (o sentido do OpenGL). No RSX, stride 0
  repete um elemento para todos os vértices; o R3 guarda um registro por draw
  assim, e cada vértice lia os registros das fitas seguintes
  (`PS3RECOMP_ENG_STRIDE0=packed` volta à leitura antiga). A tabela de render
  targets tem 512 vagas por padrão (`PS3RECOMP_ENG_SURFACE_SLOTS`; com 128 eram
  milhares de alvos expulsos por sessão).
- Colisão corrigida: o CollBroad deixa a lista de candidatos no próprio local
  store e o CollNarrow a lê por DMA pela janela de LS das threads SPU
  (EA 0xF0000000 + n*0x100000, aqui 0xF0007410). O MFC lia esse endereço como
  memória comum (zeros), então cada sonda testava 0 triângulos e o personagem
  caía através do cenário. O toolkit agora atende a janela a partir do
  contexto da lane SPURS (`spu_ls_window_copy`, spurs_policy.c). Achado com um
  replay offline do CollNarrow a partir de um snapshot ao vivo
  (`R3_COLL_SNAPSHOT`, `R3_COLL_SNAPSHOT_LR=other`).
- Corrigido o despachante rápido SPU: jobs que ocupam a memória de um policy
  module passam a usar o código residente, inclusive módulos relocáveis.
  O teste de regressão com o registro real falha antes da correção e passa
  depois. Isso, isoladamente, ainda não resolve a colisão na gameplay.
- A/B: interpretar CollBroad, CollNarrow e seus dez submódulos também
  reproduz a queda. Um HDD1 novo também não resolve; o arquivo principal
  instalado no HDD0 tem o mesmo SHA256 do disco: foi isso que apontou para o
  runtime, e não para a tradução.

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
- [x] Módulos SPU relocáveis: 184 módulos traduzidos por
  `tools/lift_r3_relocmods.py` (151 ig e 33 DEADDEAD).
- [ ] Primeiro boot: logos, o aviso de auto-save, input (o Resistance 2
  precisou de um hook de porta 0 no front-end), menus.
- [ ] A instalação no HD da primeira vez: quais arquivos o Resistance 3
  escreve, para o `PS3_GAMEDATA_MARKERS` e o `HDD_INSTALL_MARKERS` do
  launcher; os nomes dos slots de save para o gerenciador de saves.
- [x] Vídeos Bink nas filas do igPm; cinemáticas 3D também aparecem.
- [x] Colisão do jogador na primeira fase (janela de LS dos SPUs).
- [ ] Validar a campanha a 30 fps do começo ao fim (a gameplay roda a
  25-30 fps com parte do código SPU ainda interpretado).
- [ ] `tools/r3_survey.py --write-insn` e `RES_UNLOCK_FPS=1` / `RES_FOV`
  jogando; depois 60 fps.
- [ ] Medir de novo o espaço em disco de uma instalação completa (o launcher
  e o `tools/install.sh` pedem 8 GB até lá).
- [ ] Publicar o repositório (`erikomis/resistance3-recomp`, o nome que o
  updater do launcher e o clone das fontes já usam) e a primeira release do
  launcher.
- [ ] RecompLauncher: o perfil (`recomplauncher.json`), o `--prepare` sem
  janela do launcher e o `scripts/package-recomplauncher.sh` já estão aqui;
  falta uma release com esse zip, um prepare completo num Mac limpo e a
  listagem no recomplauncher.com (README do launcher, "RecompLauncher").

## Depois

- [ ] Multiplayer online. A Sony desligou os servidores do Resistance 3 junto
  com os do resto da série; os ports do Resistance 1 e 2 trazem a base no
  patch do toolkit (sockets reais `PS3_NET_ONLINE=1`, `PS3_NET_DNS`, um login
  PSN local `PS3_NP_SIGNIN=1`), tudo desligado por padrão e também neste
  patch. A campanha vem primeiro.
