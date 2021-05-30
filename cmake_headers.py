import os

UNV = 'C:/unv/Unvanquished'
DAEMON = 'C:/unv/Unvanquished/daemon'
substs = {
    '${GAMELOGIC_DIR}': UNV + '/src',
    '${LIBROCKET_DIR}': UNV + '/libs/libRocket',
}
def headers(path):
    h = []
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            if f.lower().endswith('.h'):
                h.append(dirpath.replace('\\', '/') + '/' + f)
    return h

def check(name, path, cmake, **substs):
    hdrs = headers(path)
    cmake = open(cmake).read()
    for a,b in substs.items():
        cmake = cmake.replace('${%s}' % a, b)
    print('Missing headers from %s (out of %d):' % (name, len(hdrs)))
    for h in hdrs:
        if h not in cmake:
            print(' ', h)

check('Unvanquished', UNV + '/src', UNV + '/src.cmake', GAMELOGIC_DIR=UNV+'/src')
check('librocket', UNV + '/libs/libRocket', UNV + '/libRocket.cmake', LIBROCKET_DIR=UNV+'/libs/libRocket')
check('Daemon', DAEMON + '/src', DAEMON + '/src.cmake',
      COMMON_DIR=DAEMON+'/src/common', ENGINE_DIR=DAEMON+'/src/engine', MOUNT_DIR=DAEMON+'/src')
# check('Daemon libs', DAEMON + '/libs', DAEMON + '/srclibs.cmake', LIB_DIR=DAEMON+'/libs')
