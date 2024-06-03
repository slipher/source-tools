#!/usr/bin/env python2

import os
import re

# https://stackoverflow.com/a/7392391
TEXTCHARS = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
def SeemsBinary(file):
    data = file.read(256)
    return bool(data.translate(None, TEXTCHARS))

def UniqueWords(path, subpaths=('',)):
    words = {}
    for subpath in subpaths:
        for dirpath, dirs, filenames in os.walk(os.path.join(path, subpath)):
            if '.git' in dirs:
                dirs.remove('.git')
            for filename in filenames:
                fpath = os.path.join(dirpath, filename)
                with open(fpath, 'rb') as f:
                    if SeemsBinary(f):
                        continue
                    f.seek(0)
                    for ix, line in enumerate(f):
                        for word in re.findall(r'\b[a-zA-Z_]\w+', line):
                            if word in words:
                                words[word] = None
                            else:
                                words[word] = os.path.relpath(fpath, path).replace('\\', '/'), ix + 1
    return {word:loc for word,loc in words.iteritems() if loc is not None}

def RemoveFilePrefix(pref, words):
    for word,loc in words.items():
        if loc[0].startswith(pref):
            del words[word]

def AllUniqueWords():
    words = UniqueWords(
        'C:/unv/Unvanquished',
        ['libs', 'src', 'daemon/src', 'daemon/libs', 'daemon/external_deps/windows-amd64-msvc_10'])
    RemoveFilePrefix('libs', words)
    RemoveFilePrefix('daemon/libs', words)
    RemoveFilePrefix('daemon/external_deps', words)
    return words

for word, loc in sorted(AllUniqueWords().items(), key=lambda p: p[1]):
    print '%-50s %s' % ('%s:%d' % loc, word)
