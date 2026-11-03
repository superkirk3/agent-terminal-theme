#!/usr/bin/env python3
"""Audit publishable files without printing any matched secret value."""
import argparse
import io
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '__pycache__', '.venv', 'venv'}
PRIVATE_NAMES = {'auth.json', 'credentials.json', '.credentials.json', 'install.json', 'preferences.json', 'preferences.json.lock',
                 'settings.json', 'config.toml', '.env', 'id_rsa', 'id_ed25519'}
PATTERNS = {
    'private key': rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',
    'GitHub token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'API token': rb'sk-[A-Za-z0-9_-]{24,}',
    'cloud access key': rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'Slack token': rb'xox[baprs]-[A-Za-z0-9-]{20,}',
    'personal home path': rb'(?:/Users/|/home/)[A-Za-z0-9_.-]+/',
    'Windows personal home path': rb'[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_. -]+[\\/]',
}


def png_metadata(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'): return True
    offset = 8
    while offset < len(raw):
        if offset+12 > len(raw): return True
        count = struct.unpack_from('>I', raw, offset)[0]
        kind = raw[offset+4:offset+8]
        if kind not in {b'IHDR', b'PLTE', b'IDAT', b'tRNS', b'IEND'}: return True
        offset += count+12
    return offset != len(raw)


def index_files():
    listing = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=ROOT,
                             check=True, capture_output=True).stdout
    entries = []
    for item in listing.split(b'\0'):
        if not item: continue
        metadata, name = item.split(b'\t', 1)
        mode, oid, stage = metadata.split()
        if stage != b'0': raise RuntimeError('Resolve index conflicts before auditing.')
        entries.append((Path(name.decode()), mode, oid))
    requests = b''.join(oid+b'\n' for _, _, oid in entries)
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT, input=requests,
                            check=True, capture_output=True)
    stream = io.BytesIO(result.stdout)
    for relative, mode, _ in entries:
        _, kind, size = stream.readline().split()
        if kind != b'blob': raise RuntimeError('Unexpected object type in index.')
        raw = stream.read(int(size))
        if stream.read(1) != b'\n': raise RuntimeError('Incomplete index object.')
        yield relative, mode == b'120000', raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Read actual git index blobs')
    parser.add_argument('--deny-terms-file', type=Path, help='Optional PRIVATE local list; never commit it')
    args = parser.parse_args()
    terms = []
    if args.deny_terms_file:
        terms = [line.strip().lower().encode() for line in args.deny_terms_file.read_text().splitlines() if line.strip()]
    if args.staged:
        files = index_files()
    else:
        paths = [p.relative_to(ROOT) for p in ROOT.rglob('*') if p.is_file()
                 and not any(part in EXCLUDED for part in p.relative_to(ROOT).parts)]
        files = ((relative, (ROOT/relative).is_symlink(), (ROOT/relative).read_bytes())
                 for relative in paths)
    findings = []
    count = 0
    for relative, symlink, raw in files:
        if relative.name in PRIVATE_NAMES or any(part in {'.ssh', '.aws', '.alicloud', '.codex', '.claude', '.copilot', 'backups', 'verification', 'session-registry'} for part in relative.parts):
            findings.append((relative, 'private file category'))
        if symlink:
            findings.append((relative, 'symlink requires manual review'))
            continue
        count += 1
        lowered = raw.lower() + b'\n' + relative.as_posix().lower().encode()
        if any(term in lowered for term in terms):
            findings.append((relative, 'private deny-list term'))
        if relative.suffix == '.png':
            if png_metadata(raw): findings.append((relative, 'PNG ancillary metadata'))
        elif relative.suffix not in {'.sxp', '.six', '.ans'}:
            for label, pattern in PATTERNS.items():
                if re.search(pattern, raw): findings.append((relative, label))
    for path, label in findings:
        print(f'{path}: {label}')
    print(f'Audited {count} files; {len(findings)} findings. Matched values are never printed.')
    return bool(findings)


if __name__ == '__main__': sys.exit(main())
