#!/usr/bin/env python3

import os, os.path
import re

SRC = 'C:/unv/unvanquished/daemon/src'


for dirpath, _, filenames in os.walk(SRC):
    for f in filenames:
        f = f.lower()
        if not f.endswith('.cpp'): continue
        fname = os.path.join(dirpath, f)
        includes = [l.lower() for l in open(fname) if '#include' in l]
        icommon = [i for i,l in enumerate(includes) if re.search(r'\bcommon\.h', l)]

        if not icommon:
            problem = 'Not included'
        elif len(icommon) > 1:
            problem = 'Multiply included'
        elif icommon[0] != 0:
            problem = 'Not first'
        else:
            problem = None
        if problem:
            print '%-25s %s' % (problem, fname)
