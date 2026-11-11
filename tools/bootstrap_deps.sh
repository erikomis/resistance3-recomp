#!/bin/zsh
# Install everything the port's build and the game need -- without Homebrew --
# into a per-user folder:
#
#   tools/bootstrap_deps.sh            # what is not there yet
#   tools/bootstrap_deps.sh --list     # the pinned versions, and what is installed
#   tools/bootstrap_deps.sh --check    # exit 0 when everything is installed
#
#   RES_DEPS       the folder (default:
#                  ~/Library/Application Support/resistance-recomp-3/deps)
#   RES_DEPS_WORK  scratch space for the source builds, removed when done
#                  (default: $TMPDIR/resistance3-deps-<uid>; it must not
#                  contain spaces, FFmpeg's build cannot cope with them)
#   JOBS           parallel compile jobs (default: every core)
#
# What it installs, in order (the versions are pinned below, every download
# is checked against its SHA-256):
#
#   1 CMake        Kitware's macOS universal build
#   2 Ninja        the ninja-build release
#   3 Python 3.12  astral-sh/python-build-standalone (install_only, arm64);
#                  the rebuild makes the port's .venv from it
#   4 SDL2         from source: the game's input and audio backends (a shared
#                  library; the game finds it by its absolute install name)
#   5 SPIRV-Tools  from source, with SPIRV-Headers (glslang's optimizer: the
#                  HLSL legalization passes)
#   6 glslang      from source: guest shaders HLSL -> SPIR-V
#   7 SPIRV-Cross  from source, with its C API: SPIR-V -> Metal shading
#                  language. Without 6 and 7 the Metal backend cannot draw
#                  the game's shaders.
#   8 FFmpeg       from source, LGPL, shared, only libavcodec + libavutil with
#                  the three decoders the port uses (H.264 and MPEG-2 for the
#                  movies, AC3 for the movies' sound); no programs, no
#                  network, no external libraries. The game loads it at run
#                  time (PS3RECOMP_FFMPEG_AVCODEC / _AVUTIL, set by
#                  tools/env.sh and the launcher).
#
# Everything is built with that CMake and Ninja and Apple's clang: the only
# thing the Mac needs first is the Xcode Command Line Tools
# (xcode-select --install). Each component, once installed, is stamped
# (<RES_DEPS>/.stamps/<name> holds its version) and skipped on the next run,
# so running the script again after a failure or a quit continues where it
# stopped; changing a pin here rebuilds that component. Downloads are kept in
# <RES_DEPS>/downloads (a partial one is resumed), build logs in
# <RES_DEPS>/logs. Homebrew is ignored even when it is installed.
#
# tools/install.sh uses this folder when it is there (PATH, CMAKE_PREFIX_PATH,
# HOMEBREW_PREFIX for tools/env.sh's and tools/rebuild.sh's FFmpeg headers and
# libraries); without it the port builds with Homebrew's. So does the
# launcher. (From the Resistance: Fall of Man port by way of the Resistance 2
# port, unchanged but for the default folders.)
set -e
setopt pipefail
umask 022

DEPS=${RES_DEPS:-$HOME/Library/Application Support/resistance-recomp-3/deps}
DEPS=${DEPS:a}
STAMPS=$DEPS/.stamps
DL=$DEPS/downloads
LOGS=$DEPS/logs
JOBS=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 4)}

# ---- the pins ---------------------------------------------------------------
COMPONENTS=(cmake ninja python sdl2 spirv-tools glslang spirv-cross ffmpeg)
typeset -A NAME VER URL SHA
VULKAN_SDK=vulkan-sdk-1.4.363.0
KG=https://github.com/KhronosGroup

NAME[cmake]=CMake;        VER[cmake]=4.4.4
URL[cmake]=https://github.com/Kitware/CMake/releases/download/v4.4.4/cmake-4.4.4-macos-universal.tar.gz
SHA[cmake]=4b7b73704b1db9b374e5c9ab8e17ac6148b817b6396ee75cd94a852cbac9d305

NAME[ninja]=Ninja;        VER[ninja]=1.13.2
URL[ninja]=https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-mac.zip
SHA[ninja]=c99048673aa765960a99cf10c6ddb9f1fad506099ff0a0e137ad8960a88f321b

NAME[python]=Python;      VER[python]=3.12.15+20261009
URL[python]=https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.12.15+20261009-aarch64-apple-darwin-install_only_stripped.tar.gz
SHA[python]=233f8e15255b3e1d1fd47ea5dd5230dfed803f371138e896e54d98c60ae19f6f

NAME[sdl2]=SDL2;          VER[sdl2]=2.32.10
URL[sdl2]=https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-2.32.10.tar.gz
SHA[sdl2]=5f5993c530f084535c65a6879e9b26ad441169b3e25d789d83287040a9ca5165

NAME[spirv-headers]=SPIRV-Headers; VER[spirv-headers]=$VULKAN_SDK
URL[spirv-headers]=$KG/SPIRV-Headers/archive/refs/tags/$VULKAN_SDK.tar.gz
SHA[spirv-headers]=5b3a0d099f5c7649e29c0938476c462e71d66ad89a0bde42fa1ba3eb476956c9

NAME[spirv-tools]=SPIRV-Tools; VER[spirv-tools]=$VULKAN_SDK
URL[spirv-tools]=$KG/SPIRV-Tools/archive/refs/tags/$VULKAN_SDK.tar.gz
SHA[spirv-tools]=e6c83a215538fbfd265ccf398d3877985055df1273dbed73912bd05307664688

NAME[glslang]=glslang;    VER[glslang]=$VULKAN_SDK
URL[glslang]=$KG/glslang/archive/refs/tags/$VULKAN_SDK.tar.gz
SHA[glslang]=cda24ec765e6d2845d106b7caa593f34127195a88524cf87821ff0088fb6edec

NAME[spirv-cross]=SPIRV-Cross; VER[spirv-cross]=$VULKAN_SDK
URL[spirv-cross]=$KG/SPIRV-Cross/archive/refs/tags/$VULKAN_SDK.tar.gz
SHA[spirv-cross]=f708982e88b763ef5b0394ed468fc2c3628f68cdab89f2e7a946cd628c04e721

NAME[ffmpeg]=FFmpeg;      VER[ffmpeg]=9.0.2
URL[ffmpeg]=https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz
SHA[ffmpeg]=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e

# A file that shows the component is installed (next to its stamp).
typeset -A MARK
MARK[cmake]=bin/cmake
MARK[ninja]=bin/ninja
MARK[python]=bin/python3.12
MARK[sdl2]=lib/cmake/SDL2/SDL2Config.cmake
MARK[spirv-tools]=lib/libSPIRV-Tools-opt.a
MARK[glslang]=lib/cmake/glslang/glslang-config.cmake
MARK[spirv-cross]=include/spirv_cross/spirv_cross_c.h
MARK[ffmpeg]=lib/libavcodec.dylib

# ---- helpers ----------------------------------------------------------------
fail() {
    print -u2 -r -- ""
    print -u2 -r -- "ERROR: $*"
    exit 1
}

installed() {   # <component>
    [ "$(cat "$STAMPS/$1" 2>/dev/null)" = "$VER[$1]" ] && [ -e "$DEPS/$MARK[$1]" ]
}

if [ "$1" = --list ] || [ "$1" = --check ]; then
    missing=0
    for c in $COMPONENTS; do
        if installed $c; then st=installed; else st=missing; missing=1; fi
        [ "$1" = --list ] && printf '%-12s %-24s %s\n' "$NAME[$c]" "$VER[$c]" "$st"
    done
    [ "$1" = --list ] && print -r -- "folder: $DEPS"
    exit $missing
fi
[ $# -eq 0 ] || fail "unknown argument '$1' (--list, --check, or nothing)"

# The build trees: no spaces (FFmpeg), kept out of the prefix.
WORK=${RES_DEPS_WORK:-${TMPDIR:-/tmp}/resistance3-deps-$UID}
WORK=${WORK%/}
case $WORK in *' '*) WORK=/tmp/resistance3-deps-$UID ;; esac

# Nothing from Homebrew (or MacPorts) may leak into these builds.
path=(${path:#/opt/homebrew*})
path=(${path:#/usr/local/*})
path=(${path:#/opt/local/*})
path=("$DEPS/bin" $path /usr/bin /bin /usr/sbin /sbin)
unset PKG_CONFIG_PATH CMAKE_PREFIX_PATH CPATH LIBRARY_PATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH
export PKG_CONFIG_LIBDIR=$DEPS/lib/pkgconfig
export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion 2>/dev/null | cut -d. -f1).0}

# ---- what the Mac must have -------------------------------------------------
[ "$(uname -s)" = Darwin ] || fail "this installer is for macOS; this is $(uname -s)."
[ "$(uname -m)" = arm64 ] || fail "this installer is for Apple-silicon Macs (arm64); this Mac is $(uname -m)."
if ! /usr/bin/xcode-select -p >/dev/null 2>&1 || ! /usr/bin/xcrun --find clang >/dev/null 2>&1; then
    fail "Apple's Command Line Tools are not installed. Run: xcode-select --install, wait for Apple's installer to finish, then run this again."
fi

todo=()
for c in $COMPONENTS; do installed $c || todo+=$c; done
if (( ${#todo} == 0 )); then
    print -r -- "Everything is already installed in $DEPS"
    exit 0
fi

mkdir -p "$DEPS" "$STAMPS" "$DL" "$LOGS" "$DEPS/bin" "$DEPS/opt" || fail "cannot create $DEPS"
# 0.5 GB stays (with the downloads); the build trees on the way need more.
free_mb=$(df -m "$DEPS" | awk 'NR==2 {print $4}')
if [ -n "$free_mb" ] && (( free_mb < 2048 )); then
    fail "not enough free disk space: $((free_mb / 1024)) GB free on the disk that holds $DEPS, about 2 GB are needed. Free some space and run this again."
fi
mkdir -p "$WORK" || fail "cannot create $WORK"

fetch() {   # <key> -> $REPLY: the verified file
    local key=$1 url=$URL[$1] want=$SHA[$1]
    local f=$DL/$key-${url:t}   # the Khronos archives all end in <tag>.tar.gz
    REPLY=$f
    if [ -f "$f" ] && [ "$(shasum -a 256 "$f" | cut -d' ' -f1)" = "$want" ]; then
        return 0
    fi
    print -r -- "    downloading ${url:t}"
    local ok=1
    /usr/bin/curl -fL -sS --retry 4 --retry-delay 3 --connect-timeout 30 -C - -o "$f.part" "$url" || ok=0
    if [ -f "$f.part" ] && [ "$(shasum -a 256 "$f.part" | cut -d' ' -f1)" = "$want" ]; then
        mv "$f.part" "$f"
        return 0
    fi
    if (( ok )); then
        rm -f "$f.part"
        fail "the download of $NAME[$key] ($url) is not the expected file (SHA-256 mismatch). It was deleted; run this again. If it keeps happening, report it."
    fi
    fail "could not download $NAME[$key] from $url. Check the internet connection and run this again: it continues where it stopped."
}

LOG=
run() {   # <command...> -> appended to $LOG; on failure, its end and a plain message
    if ! "$@" >>"$LOG" 2>&1; then
        print -u2 -r -- "---- the end of $LOG ----"
        tail -n 40 "$LOG" >&2
        # the build trees go (they can be large: a full disk is a usual cause);
        # the downloads stay for the next run
        rm -rf "$WORK/build" "$WORK/src"
        fail "building $CUR failed (the full log is $LOG). Run this again; if it fails the same way, report it with that log."
    fi
}

unpack() {   # <archive> <dir>: a source tarball, its top folder dropped
    rm -rf "$2"; mkdir -p "$2"
    tar -xf "$1" -C "$2" --strip-components 1 || fail "could not unpack ${1:t} (a damaged download? delete it from $DL and run this again)"
}

# CMake is run through a link to its app bundle from the build folder: CMake
# keeps the path it was started by as CMAKE_COMMAND, and some projects' install
# code (SDL2's) splits an unquoted CMAKE_COMMAND at the space of
# "Application Support".
CMAKE=$WORK/CMake.app/Contents/bin/cmake
cmake_build() {   # <name> <source dir> [cmake args...]
    local name=$1 src=$2 b=$WORK/build/$1
    shift 2
    ln -sfn "$DEPS/opt/CMake.app" "$WORK/CMake.app"
    rm -rf "$b"
    run "$CMAKE" -S "$src" -B "$b" -G Ninja \
        -DCMAKE_MAKE_PROGRAM="$DEPS/bin/ninja" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$DEPS" -DCMAKE_INSTALL_LIBDIR=lib \
        -DCMAKE_PREFIX_PATH="$DEPS" \
        -DCMAKE_IGNORE_PREFIX_PATH="/opt/homebrew;/usr/local;/opt/local" \
        -DCMAKE_FIND_FRAMEWORK=LAST \
        -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DCMAKE_C_COMPILER=/usr/bin/clang -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        -DPython3_EXECUTABLE="$DEPS/opt/python/bin/python3.12" \
        "$@"
    run "$CMAKE" --build "$b" -j "$JOBS"
    run "$CMAKE" --install "$b"
    rm -rf "$b"
}

# ---- the components ---------------------------------------------------------
do_cmake() {
    fetch cmake
    local t=$WORK/src/cmake
    rm -rf "$t"; mkdir -p "$t"
    tar -xf "$REPLY" -C "$t" --strip-components 1 || fail "could not unpack CMake"
    rm -rf "$DEPS/opt/CMake.app"
    mv "$t/CMake.app" "$DEPS/opt/CMake.app"
    for x in cmake ctest cpack; do ln -sfn "../opt/CMake.app/Contents/bin/$x" "$DEPS/bin/$x"; done
    "$DEPS/bin/cmake" --version >/dev/null 2>&1 || fail "the downloaded CMake does not run on this Mac"
    rm -rf "$t"
}

do_ninja() {
    fetch ninja
    /usr/bin/unzip -o -q "$REPLY" ninja -d "$DEPS/bin" || fail "could not unpack Ninja"
    chmod 755 "$DEPS/bin/ninja"
    "$DEPS/bin/ninja" --version >/dev/null 2>&1 || fail "the downloaded Ninja does not run on this Mac"
}

do_python() {
    fetch python
    local t=$WORK/src/python
    rm -rf "$t"; mkdir -p "$t"
    tar -xf "$REPLY" -C "$t" || fail "could not unpack Python"
    rm -rf "$DEPS/opt/python"
    mv "$t/python" "$DEPS/opt/python"
    ln -sfn ../opt/python/bin/python3.12 "$DEPS/bin/python3.12"
    ln -sfn python3.12 "$DEPS/bin/python3"
    "$DEPS/opt/python/bin/python3.12" -c 'import ssl, venv, ensurepip' >/dev/null 2>&1 ||
        fail "the downloaded Python does not run on this Mac"
    rm -rf "$t"
}

do_sdl2() {
    fetch sdl2
    unpack "$REPLY" "$WORK/src/sdl2"
    # An absolute install name: the game finds the library without an rpath.
    cmake_build sdl2 "$WORK/src/sdl2" \
        -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF -DSDL_TESTS=OFF \
        -DCMAKE_INSTALL_NAME_DIR="$DEPS/lib"
    rm -rf "$WORK/src/sdl2"
}

do_spirv-tools() {
    fetch spirv-headers; local h=$REPLY
    fetch spirv-tools; local s=$REPLY
    unpack "$h" "$WORK/src/spirv-headers"
    unpack "$s" "$WORK/src/spirv-tools"
    cmake_build spirv-headers "$WORK/src/spirv-headers" -DSPIRV_HEADERS_ENABLE_TESTS=OFF
    cmake_build spirv-tools "$WORK/src/spirv-tools" \
        -DSPIRV-Headers_SOURCE_DIR="$WORK/src/spirv-headers" \
        -DBUILD_SHARED_LIBS=OFF -DSPIRV_SKIP_TESTS=ON -DSPIRV_SKIP_EXECUTABLES=ON \
        -DSPIRV_WERROR=OFF -DSPIRV_TOOLS_BUILD_STATIC=ON
    rm -rf "$WORK/src/spirv-headers" "$WORK/src/spirv-tools"
}

do_glslang() {
    fetch glslang
    unpack "$REPLY" "$WORK/src/glslang"
    cmake_build glslang "$WORK/src/glslang" \
        -DBUILD_SHARED_LIBS=OFF -DENABLE_OPT=ON -DALLOW_EXTERNAL_SPIRV_TOOLS=ON \
        -DENABLE_HLSL=ON -DGLSLANG_TESTS=OFF -DENABLE_GLSLANG_BINARIES=OFF \
        -DGLSLANG_ENABLE_INSTALL=ON
    rm -rf "$WORK/src/glslang"
}

do_spirv-cross() {
    fetch spirv-cross
    unpack "$REPLY" "$WORK/src/spirv-cross"
    cmake_build spirv-cross "$WORK/src/spirv-cross" \
        -DSPIRV_CROSS_SHARED=OFF -DSPIRV_CROSS_STATIC=ON -DSPIRV_CROSS_CLI=OFF \
        -DSPIRV_CROSS_ENABLE_TESTS=OFF -DSPIRV_CROSS_ENABLE_C_API=ON \
        -DSPIRV_CROSS_ENABLE_MSL=ON -DSPIRV_CROSS_SKIP_INSTALL=OFF
    # The toolkit's CMake asks pkg-config first, and pkg-config output cannot
    # carry a path with a space; without the .pc files it finds the header and
    # the library itself.
    rm -f "$DEPS"/lib/pkgconfig/spirv-cross*.pc
    rm -rf "$WORK/src/spirv-cross"
}

do_ffmpeg() {
    fetch ffmpeg
    local src=$WORK/src/ffmpeg b=$WORK/build/ffmpeg link=$WORK/prefix
    unpack "$REPLY" "$src"
    rm -rf "$b"; mkdir -p "$b"
    # FFmpeg's configure and Makefiles break on a path with a space in it,
    # and the default prefix has one ("Application Support"): install
    # through a link without one. The libraries name each other as
    # @loader_path/..., so nothing in them points at the link.
    ln -sfn "$DEPS" "$link"
    ( cd "$b" && run "$src/configure" --prefix="$link" --install-name-dir='@loader_path' \
        --cc=/usr/bin/clang --arch=arm64 --enable-shared --disable-static \
        --disable-programs --disable-doc --disable-network --disable-autodetect \
        --disable-everything --disable-avdevice --disable-avformat --disable-avfilter \
        --disable-swscale --disable-swresample \
        --enable-decoder=h264,mpeg2video,ac3 )
    ( cd "$b" && run /usr/bin/make -j "$JOBS" && run /usr/bin/make install )
    rm -f "$DEPS"/lib/pkgconfig/libav{codec,util}.pc   # they name the link
    rm -rf "$b" "$src" "$link"
}

# ---- run ----------------------------------------------------------------------
n=${#COMPONENTS}; i=0
start=$SECONDS
for c in $COMPONENTS; do
    i=$((i + 1))
    if installed $c; then
        print -r -- "==> [$i/$n] $NAME[$c] $VER[$c] (already installed)"
        continue
    fi
    print -r -- "==> [$i/$n] $NAME[$c] $VER[$c]"
    t0=$SECONDS
    CUR=$NAME[$c]
    LOG=$LOGS/$c.log
    : >"$LOG"
    rm -f "$STAMPS/$c"
    do_$c
    [ -e "$DEPS/$MARK[$c]" ] || fail "$NAME[$c] was built but $DEPS/$MARK[$c] is not there (see $LOG)"
    print -r -- "$VER[$c]" >"$STAMPS/$c"
    print -r -- "    installed in $((SECONDS - t0)) s"
done
rm -f "$WORK/CMake.app"
rmdir "$WORK/src" "$WORK/build" "$WORK" 2>/dev/null || true

{
    print -r -- "# tools/bootstrap_deps.sh, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for c in $COMPONENTS; do print -r -- "$c $VER[$c]"; done
} >"$DEPS/manifest.txt"
print -r -- "    all set in $((SECONDS - start)) s: $DEPS ($(du -sh "$DEPS" | cut -f1) on disk)"
