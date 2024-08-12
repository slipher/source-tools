#!/usr/bin/env python3
"""Makes a directory of which shader keywords are used by which shader files.

Note: the "parser" is very simplistic. It detects some things as keywords which aren't,
such as the state string which follows the `when` keyword.
"""

from collections import defaultdict
import os
import re
import sys
import zipfile

log = lambda *a: print(*a, file=sys.stderr)

paks = []
for path in sys.argv[1:]:
    for dirname, _, basenames in os.walk(path):
        for basename in basenames:
            if basename[-4:].lower() in ('.pk3', '.dpk'):
                paks.append(os.path.join(dirname, basename))
log('Searching', len(paks), 'paks')

kwdir = defaultdict(list)

for pak in paks:
    try:
        z = zipfile.ZipFile(pak)
    except (zipfile.BadZipFile, FileNotFoundError):
        log("Couldn't open", pak)
        continue
    for name in z.namelist():
        m = re.fullmatch(r'scripts/.*[.]shader', name, re.IGNORECASE)
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
        for token in re.findall(rb'[{}]|[^\s{}]+/[^\s{}]+|[a-zA-Z]\w*', text):
            if len(token) > 1 and b'/' not in token:
                kws[token.lower().decode('utf8')] += 1
        for kw, count in kws.items():
            kwdir[kw].append((pak, name, count))

for kw, occurrences in sorted(kwdir.items()):
    print(kw)
    for pak, script, count in sorted(occurrences):
        print('\t' + pak, script, count)
