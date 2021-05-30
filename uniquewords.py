import os
import re

def UniqueWords(path, subpaths=('',)):
    words = {}
    for subpath in subpaths:
        for dirpath, _, filenames in os.walk(os.path.join(path, subpath)):
            for filename in filenames:
                fpath = os.path.join(dirpath, filename)
                for ix, line in enumerate(open(fpath)):
                    for word in re.findall(r'\b[a-zA-Z_]\w*', line):
                        if word in words:
                            words[word] = None
                        else:
                            words[word] = os.path.relpath(fpath, path) + ':' + str(ix + 1)
    return {word:loc for word,loc in words.iteritems() if loc is not None}

def RemoveFilePrefix(pref, words):
    for word,loc in words.items():
        if loc.startswith(pref):
            del words[word]

def DaemonSrcUniqueWords():
    return UniqueWords('C:/unv/Unvanquished/daemon/src')

def UnvUniqueWords():
    words = UniqueWords('C:/unv/Unvanquished/', ['libs', 'src', 'daemon/src'])
    RemoveFilePrefix('libs', words)
    RemoveFilePrefix('daemon', words)
    return words

for word, loc in UnvUniqueWords().iteritems():
    print '%-50s %s' % (loc, word)
