#!/bin/zsh
# Regenerate docs/screenshots/ (1280x800, one at 880x900) from the built frontend and the fake
# backend in scripts/ui-mock.js: no game art, no running game.
#
#   npm run build && scripts/screenshots.sh [chrome-or-headless-shell]
#
# The page is served from a temporary copy of dist/ with ui-mock.js loaded
# before the app and CSS transitions off (headless captures catch switches
# mid-animation otherwise); each screen is chosen through the mock's query
# string (?view=<page>[:<tab>]&lang=en&noBuilds=1...). The browser defaults to
# Playwright's chrome-headless-shell when it is installed (Google Chrome's own
# --headless leaves a black patch on long pages), else Google Chrome.
set -e
here=${0:A:h}; root=${here:h}
browser=$1
if [ -z "$browser" ]; then
    for c in ~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell(N) \
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
        [ -x "$c" ] && browser=$c
    done
fi
[ -x "$browser" ] || { echo "no browser: pass the path of Chrome or chrome-headless-shell" >&2; exit 1; }
[ -f "$root/dist/index.html" ] || { echo "no dist/: npm run build first" >&2; exit 1; }
tmp=$(mktemp -d); trap 'kill $srv 2>/dev/null; rm -rf "$tmp"' EXIT
cp -R "$root/dist/." "$tmp/"; cp "$here/ui-mock.js" "$tmp/"
python3 - "$tmp/index.html" <<'PY'
import sys; p = sys.argv[1]; s = open(p).read(); i = s.index('<script type="module"')
s = s[:i] + '<style>*,*::before,*::after{transition:none!important;animation:none!important}</style>\n    <script src="/ui-mock.js"></script>\n    ' + s[i:]
open(p, "w").write(s)
PY
port=4173
(cd "$tmp" && exec python3 -m http.server $port --bind 127.0.0.1 >/dev/null 2>&1) & srv=$!
sleep 1
out=$root/docs/screenshots; mkdir -p "$out"
shot() {   # <name> <query> [<width>,<height>]
    "$browser" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$tmp/profile" --window-size=${3:-1280,800} \
        --virtual-time-budget=5000 --screenshot="$out/$1.png" "http://127.0.0.1:$port/?$2" >/dev/null 2>&1
    echo "$out/$1.png"
}
shot home "view=home"
shot home.en "view=home&lang=en"
shot home-first-boot "view=home&firstBoot=1"
shot home-no-disc "view=home&noDisc=1"
shot home-not-built "view=home&noBuilds=1"
shot graphics "view=graphics"
shot performance "view=performance"
shot performance.en "view=performance&lang=en"
shot game "view=game"
shot controls "view=controls"
shot advanced-install "view=advanced:install"
shot advanced-install-problems "view=advanced:install&prereqProblems=1"
shot advanced-install-narrow "view=advanced:install&prereqProblems=1" 880,900
shot advanced-updates "view=advanced:updates"
shot advanced-log "view=advanced:log"
shot advanced-diagnostics "view=advanced:diagnostics"
shot advanced-env "view=advanced:env"
