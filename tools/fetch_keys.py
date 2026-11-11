#!/usr/bin/env python3
"""Fetch the keys that decrypt the disc's executables, from RPCS3's public source.

    tools/fetch_keys.py                 # write the key file if it is not there yet
    tools/fetch_keys.py --force         # download and write it again
    tools/fetch_keys.py --source FILE   # use a key_vault.cpp you already have

No key is in this repository. The disc's EBOOT.BIN is a SELF encrypted with
the PS3's application keys ("appldr", program type APP), and
those keys are published in RPCS3's source code, rpcs3/Crypto/key_vault.cpp.
This downloads that one file from GitHub at a pinned commit, checks its
SHA-256 (so the file is exactly the one this was tested with, whatever the
network or TLS in between), takes the APP entries (key revision, erk, riv) out
of KeyVault::LoadSelfAPPKeys, and writes them in scetool's key-file format
for tools/decrypt_self.py.

The key file goes to a per-user folder outside the repository, readable only
by you (mode 600):

    macOS  ~/Library/Application Support/resistance-recomp-3/keys/self_keys.txt
    other  $XDG_DATA_HOME (~/.local/share)/resistance-recomp-3/keys/self_keys.txt

--out or RES_SELF_KEYS put it elsewhere. The path is printed on stdout (and
nothing else); progress and errors go to stderr. No key is ever printed.

Only the Python standard library is used, so this runs before the toolkit's
Python packages are installed.
"""
import argparse
import hashlib
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

# The last RPCS3 commit that changed key_vault.cpp when this was written
# ("Use std::string_view in crypto code", 2026-06-16), and the SHA-256 of the
# file at that commit. A hash is not a key: it only says which file is right.
RPCS3_COMMIT = 'b8ca6d953f734900c23f2cfbe79a36e598171553'
KEY_VAULT_SHA256 = 'a2947ff6b681258c198552ec6344e16685e2df649018206daa3f41a0a1aadbd7'
KEY_VAULT_URL = ('https://raw.githubusercontent.com/RPCS3/rpcs3/%s/rpcs3/Crypto/key_vault.cpp'
                 % RPCS3_COMMIT)

# Key revisions every copy of the table has: 0x0001 (the Resistance 2 disc,
# Resistance: Fall of Man 01.00) and 0x0002 (its v1.7 update). Every APP entry
# is written, so the later revision Resistance 3's 2011 EBOOT is signed with
# is in the file too (tools/decrypt_self.py --info names the one it needs);
# these two are only a sanity check of the table.
NEEDED_REVISIONS = (0x0001, 0x0002)


def default_path():
    if os.environ.get('RES_SELF_KEYS'):
        return os.environ['RES_SELF_KEYS']
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        base = os.path.join(home, 'Library', 'Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
    return os.path.join(base, 'resistance-recomp-3', 'keys', 'self_keys.txt')


def log(msg):
    print(msg, file=sys.stderr)


class FetchError(Exception):
    pass


def download(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': 'resistance3-recomp fetch_keys.py'})

    def get(ctx):
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()
    try:
        try:
            return get(ssl.create_default_context())
        except urllib.error.URLError as e:
            if not isinstance(e.reason, ssl.SSLCertVerificationError):
                raise
            # A python.org Python on macOS has no CA certificates until its
            # "Install Certificates.command" is run. The file is checked
            # against its pinned SHA-256 below, so a connection that cannot
            # be verified still cannot hand us a different file.
            log('  (this Python cannot verify GitHub\'s certificate; the file is checked by its SHA-256 instead)')
            return get(ssl._create_unverified_context())
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, 'reason', e)
        raise FetchError(
            'could not download the decryption keys from GitHub (%s).\n'
            'Check that this computer is connected to the internet and try again.\n'
            'They come from: %s' % (reason, url))


def parse_app_keys(text):
    """[(revision, erk hex, riv hex)] from KeyVault::LoadSelfAPPKeys, in file
    order (RPCS3 takes the first entry of a revision; so does decrypt_self.py)."""
    m = re.search(r'void\s+KeyVault::LoadSelfAPPKeys\s*\(\s*\)\s*\{(.*?)\n\}', text, re.S)
    if not m:
        raise FetchError('key_vault.cpp has no KeyVault::LoadSelfAPPKeys')
    entry = re.compile(
        r'sk_APP_arr\.emplace_back\(\s*0x[0-9A-Fa-f]+\s*,\s*0x[0-9A-Fa-f]+\s*,\s*0x([0-9A-Fa-f]+)\s*,'
        r'\s*KEY_APP\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"')
    keys, seen = [], set()
    for rev, erk, riv in entry.findall(m.group(1)):
        rev = int(rev, 16)
        if len(erk) != 64 or len(riv) != 32 or rev in seen:
            continue
        seen.add(rev)
        keys.append((rev, erk.upper(), riv.upper()))
    missing = [r for r in NEEDED_REVISIONS if r not in seen]
    if missing:
        raise FetchError('key_vault.cpp has no APP key for revision %s'
                         % ', '.join('0x%04X' % r for r in missing))
    return keys


def key_file_text(keys, source):
    out = ['# SELF keys for program type APP (appldr), in scetool\'s key-file format,',
           '# for tools/decrypt_self.py. Written by tools/fetch_keys.py from',
           '# %s' % source,
           '# Do not share this file or put it in a repository.', '']
    for rev, erk, riv in keys:
        out += ['[appldr_%04X]' % rev, 'type=SELF', 'revision=%04X' % rev, 'self_type=APP',
                'erk=%s' % erk, 'riv=%s' % riv, '']
    return '\n'.join(out)


def write_private(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = path + '.tmp'
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    # Created 600 from the start, so the keys are never readable by others,
    # not even for a moment.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='ascii') as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def usable(path):
    """True when the key file is there and has the APP keys the game needs."""
    try:
        with open(path, encoding='ascii', errors='replace') as f:
            text = f.read()
    except OSError:
        return False
    revs = {int(r, 16) for r in re.findall(r'^revision=([0-9A-Fa-f]+)\s*$', text, re.M)}
    return all(r in revs for r in NEEDED_REVISIONS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', default=default_path(), help='key file to write (default: %(default)s)')
    ap.add_argument('--force', action='store_true', help='download and write it even if it is there')
    ap.add_argument('--source', help='a key_vault.cpp already on disk (still checked by its SHA-256)')
    ap.add_argument('--timeout', type=float, default=60, help='download timeout, seconds (default 60)')
    a = ap.parse_args(argv)
    path = os.path.abspath(os.path.expanduser(a.out))

    if not a.force and usable(path):
        print(path)
        return 0
    try:
        if a.source:
            with open(a.source, 'rb') as f:
                raw = f.read()
            source = os.path.abspath(a.source)
        else:
            log('downloading the decryption keys from RPCS3\'s source code on GitHub...')
            raw = download(KEY_VAULT_URL, a.timeout)
            source = KEY_VAULT_URL
        got = hashlib.sha256(raw).hexdigest()
        if got != KEY_VAULT_SHA256:
            raise FetchError('key_vault.cpp is not the expected file '
                             '(SHA-256 %s, expected %s); nothing was written' % (got, KEY_VAULT_SHA256))
        keys = parse_app_keys(raw.decode('utf-8', 'replace'))
        write_private(path, key_file_text(keys, source))
    except (FetchError, OSError) as e:
        log('error: %s' % e)
        return 1
    log('  %d key sets written to %s' % (len(keys), path))
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
