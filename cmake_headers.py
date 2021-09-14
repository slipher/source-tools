#!/usr/bin/env python3

import os

UNV = 'C:/unv/Unvanquished'
DAEMON = 'C:/unv/Unvanquished/daemon'

def headers(path, ignore):
    path = os.path.normpath(path)
    ignore = [os.path.normpath(os.path.join(path, i)) for i in ignore]
    h = []
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            f = os.path.normpath(os.path.join(dirpath, f))
            if f.lower().endswith('.h') and not any(f.startswith(i) for i in ignore):
                h.append(f.replace('\\', '/'))
    return h

def check(name, path, cmake, ignore, **substs):
    hdrs = headers(path, ignore)
    cmake = open(cmake).read()
    for a,b in substs.items():
        cmake = cmake.replace('${%s}' % a, b)
    print('Missing headers from %s (out of %d):' % (name, len(hdrs)))
    for h in hdrs:
        if h not in cmake:
            print('  ' + h)

check('Unvanquished', UNV + '/src', UNV + '/src.cmake', ['sgame/components/skeletons/', 'utils/cbse/templates/', 'sgame/backend/'], GAMELOGIC_DIR=UNV+'/src')
check('generated CBSE', UNV + '/src/sgame/backend', DAEMON + '/cmake/DaemonCBSE.cmake', [], output=UNV+'/src/sgame')
check('librocket', UNV + '/libs/libRocket', UNV + '/libRocket.cmake', [], LIBROCKET_DIR=UNV+'/libs/libRocket')
check('Daemon', DAEMON + '/src', DAEMON + '/src.cmake', [],
      COMMON_DIR=DAEMON+'/src/common', ENGINE_DIR=DAEMON+'/src/engine', MOUNT_DIR=DAEMON+'/src')
# check('Daemon libs', DAEMON + '/libs', DAEMON + '/srclibs.cmake', LIB_DIR=DAEMON+'/libs')
