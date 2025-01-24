#!/usr/bin/env python3
"""Makes a directory of which shader/particle/trail keywords are used by which files.

Note: the "parser" is very simplistic. It detects some things as keywords which aren't,
such as single-word shader names referenced in particle files.
"""

from collections import defaultdict
import os
import re
import sys
import zipfile

log = lambda *a: print(*a, file=sys.stderr)

thing = sys.argv[1]
assert thing in ('shader', 'particle', 'trail')

paks = []
for path in sys.argv[2:]:
    if os.path.isdir(path):
        for dirname, _, basenames in os.walk(path):
            for basename in basenames:
                if basename[-4:].lower() in ('.pk3', '.dpk'):
                    paks.append(os.path.join(dirname, basename))
    else:
        with open(path) as f:
            for line in f:
                paks.append(line.strip('\n'))
log('Searching', len(paks), 'paks')

kwdir = defaultdict(list)

for pak in paks:
    try:
        z = zipfile.ZipFile(pak)
    except (zipfile.BadZipFile, FileNotFoundError):
        log("Couldn't open", pak)
        continue
    for name in z.namelist():
        m = re.fullmatch(r'scripts/.*[.]' + thing, name, re.IGNORECASE)
        if not m:
            continue
        try:
            f = z.open(name)
            text = f.read()
            f.close()
        except zipfile.BadZipFile:
            log('Bad zip file:', pak)
            continue
        text = re.sub(rb'//.*|/[*][.\n]*[*]/', b'', text)
        kws = defaultdict(int)
        blevel = 0
        for token in re.findall(rb'[{}]|[^\s{}]+[/\\][^\s{}]+|[a-zA-Z]\w*', text):
            if token == b'{':
                blevel += 1
            elif token == b'}':
                if blevel == 0:
                    log('Unexpected closing brace', pak, name)
                else:
                    blevel -= 1
            elif blevel and len(token) > 1 and b'/' not in token and b'\\' not in token:
                kws[token.lower().decode('utf8')] += 1
        if blevel != 0:
            log('Unclosed brace', pak, name)
        for kw, count in kws.items():
            kwdir[kw].append((pak, name, count))

for kw, occurrences in sorted(kwdir.items()):
    print(kw)
    for pak, script, count in sorted(occurrences):
        print('\t' + pak, script, count)
