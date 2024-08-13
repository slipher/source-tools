#!/usr/bin/env python3

from collections import defaultdict
import hashlib
import os
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

hashdir = defaultdict(list)

for pak in paks:
    assert '\n' not in pak
    try:
        z = zipfile.ZipFile(pak)
    except (zipfile.BadZipFile, FileNotFoundError):
        log("Couldn't open", pak)
        continue
    z.close()

    f = open(pak, 'rb')
    md5 = hashlib.file_digest(f, "md5")
    f.close()
    hashdir[md5.hexdigest()].append(pak)

for md5, paks in hashdir.items():
    print('MD5SUM', md5)
    print(paks[0])
    for pak in paks[1:]:
        print('DUPLICATE', pak)

