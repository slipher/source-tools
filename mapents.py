#!/usr/bin/env python3

from collections import defaultdict
import os
import re
import sys
import zipfile
import Bsp

log = lambda *a: print(*a, file=sys.stderr)

paks = []
for path in sys.argv[1:]:
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

entdir = defaultdict(list)
for pak in paks:
    try:
        z = zipfile.ZipFile(pak)
    except (zipfile.BadZipFile, FileNotFoundError):
        log("Couldn't open", pak)
        continue
    for name in z.namelist():
        m = re.fullmatch(r'maps/([^/\\]+)[.]bsp', name, re.IGNORECASE)
        if not m:
            continue
        mapname = m.group(1).partition('_')[0]
        bsp = Bsp.Bsp()
        try:
            bsp.bsp_file = z.open(name)
        except zipfile.BadZipFile:
            log('Bad zip file:', pak)
            continue
        bsp.readLump('entities')
        lump = bsp.bsp_parser_dict["lump_dict"]["entities"]()
        wat = bsp.lump_dict["entities"]
        ents = defaultdict(int)
        allattrs = defaultdict(set)
        while len(wat) > 1:
            m = re.match(rb'\{\n("[^"]*" "[^"]*" *\n)*\}\n*', wat)
            if not m:
                log('Parsing entities from', pak, 'failed here:', repr(wat[:200]))
                break
            wat = wat[m.end():]
            attrs = dict(re.findall(rb'"([^"]*)" "([^"]*)"', m.group(0)))
            if b"classname" in attrs:
                classname = attrs.pop(b"classname").decode('ascii')
                ents[classname] += 1
                allattrs[classname].update(attrs.keys())
            else:
                log('No classname in entity in', pak, '-', m.group(0))
        for classname, count in ents.items():
            entdir[classname].append((mapname, count, pak, sorted(k.decode('ascii') for k in allattrs[classname])))

for classname, occurrences in sorted(entdir.items()):
    print(classname)
    for mapname, count, pak, attrs in sorted(occurrences):
        print('\t' + mapname, count, pak, *attrs)
