#!/usr/bin/env python3

import os, os.path
import re

def check(src, header):
    header = header.encode('ascii')
    for dirpath, _, filenames in os.walk(src):
        if dirpath.endswith('skeletons'): continue
        for f in filenames:
            if not f.endswith('.cpp'): continue
            fname = os.path.join(dirpath, f)
            includes = [re.search(br'["<](.*)[">]', l).group(1)
                        .split(b'/')[-1]
                        for l in open(fname, 'rb')
                        if re.match(br'\s*#\s*include.*["<]', l)]
            icommon = [i for i,l in enumerate(includes) if l == header]

            if not icommon:
                problem = 'Not included'
            elif len(icommon) > 1:
                problem = 'Multiply included'
            elif icommon[0] != 0:
                problem = 'Not first'
            else:
                problem = None
            if problem:
                print('%-25s %s' % (problem, fname))

check('C:/unv/Unvanquished/daemon/src', 'Common.h')
print()
check('C:/unv/Unvanquished/src', 'Common.h')
