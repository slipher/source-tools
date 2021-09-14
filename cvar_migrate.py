#!/usr/bin/env python3

# How I got it working:
# - Install:
#   - Clang, with the Visual Studio installer
#   - Ninja (executable from Github release)
#   - python3 -m pip install libclang (there's also a "clang" package with the same modules; not sure how it's different)
# - Create compilation db with clang-cl:
#   - Open "x64 Native Tools Command Prompt for VS 2019"
#   - Run cmake with options -G Ninja -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl -DUSE_PRECOMPILED_HEADER=0 -DCMAKE_EXPORT_COMPILE_COMMANDS=1
# - Run the Ninja build (semi-optional, there are just a few files which depend on generated files)
# - Run this script in a normal command prompt

import argparse
import collections
from concurrent import futures
import difflib
import os
import re
import subprocess
import sys
import tempfile

import colorama
from clang import cindex
from clang.cindex import CursorKind

sys.stdout.reconfigure(encoding='utf-8')
colorama.init()

parser = argparse.ArgumentParser()
parser.add_argument('-b', type=str, help='build directory (with comp db)', default='C:/unv/st/spm')
parser.add_argument('-f', type=str, help='substring to match translation unit filename', default='')
parser.add_argument('-j', type=int, help='compiler threads', default=6)
parser.add_argument('-v', type=str, help='prefix for cvars to match', default='')
parser.add_argument('-T', action='store_false', help='disable text matches')
parser.add_argument('-p', action='store_true', help='interactively apply patches')
argv = parser.parse_args()
argv.v = argv.v.lower()
editor = os.getenv('EDITOR', 'C:/Program Files/Git/usr/bin/vim.exe')

cdb = cindex.CompilationDatabase.fromDirectory(argv.b)
index = cindex.Index.create()

class CvarLocs:
    def __init__(self):
        self.table = set()
        self.text = set()

        self.fw_decls = set()
        self.defs = set()
        self.int = set()
        self.float = set()
        self.string = set()
        self.other = set()

        self.name = set()
        self.flags = []

    def groups(self): # excluding text
        return [self.fw_decls, self.defs, self.int, self.float, self.string, self.other]

    def allgroups(self):
        return self.groups() + [self.table, self.text]

    def table_del(self):
        for g in (self.text, *self.groups()):
            g -= {loc for loc in g if any(tloc[:2] == loc[:2] for tloc in self.table)}

locmap = collections.defaultdict(CvarLocs)

def my_loc(cur):
    return (os.path.normpath(cur.location.file.name).replace('\\', '/'), cur.location.line, cur.location.column)


texts = {}
def get_file(f, cache=True):
    if not cache:
        return open(f, encoding='utf8').read().splitlines()
    if f not in texts:
        texts[f] = open(f, encoding='utf8').read().splitlines()
    return texts[f]

def locline(myloc):
    file, line, _ = myloc
    return get_file(file)[line - 1]

def handle_reference(cur, p):
    if cur.kind != CursorKind.DECL_REF_EXPR:
        return False
    if p.kind != CursorKind.MEMBER_REF_EXPR:
        return False

    member = p.referenced
    assert member.kind == CursorKind.FIELD_DECL
    if member.spelling == 'integer':
        locmap[cur.spelling].int.add(my_loc(cur))
    elif member.spelling == 'value':
        locmap[cur.spelling].float.add(my_loc(cur))
    elif member.spelling == 'string':
        locmap[cur.spelling].string.add(my_loc(cur))
    else:
        return False
    return True

def handle_unary(cur):
    if cur.kind != CursorKind.UNARY_OPERATOR:
        return False
    if next(iter(cur.get_tokens())).spelling != '&':
        return False
    operand, = cur.get_children()
    if operand.kind != CursorKind.DECL_REF_EXPR:
        return False
    if list(operand.get_children()):
        return False
    tok, = operand.get_tokens()
    m = re.match('^[a-z]\w*$', tok.spelling)
    if not m:
        return False
    locmap[m.group(0)].other.add(my_loc(cur))
    return True

def get_source(cur): # must be on 1 line
    assert cur.extent.start.file.name == cur.extent.end.file.name
    assert cur.extent.start.line == cur.extent.end.line
    return get_file(cur.extent.start.file.name)[cur.extent.start.line-1][cur.extent.start.column-1:cur.extent.end.column-1]

def handle_table(cur):
    fields = [f.spelling for f in cur.type.get_fields()]
    values = list(cur.get_children())
    assert len(fields) == len(values)
    for field, value in zip(fields, values):
        if field == 'vmCvar':
            if value.kind == CursorKind.CXX_NULL_PTR_LITERAL_EXPR:
                return
            assert value.kind == CursorKind.UNARY_OPERATOR
            amp, name = (t.spelling for t in value.get_tokens())
            assert amp == '&'
            assert re.match(r'^[a-z]\w*$', name)
            locs = locmap[name]
            locs.table.add(my_loc(cur))
        elif field == 'cvarName':
            assert value.kind == CursorKind.STRING_LITERAL
            tok, = value.get_tokens()
            m = re.match(r'^"([a-z]\w*)"$', tok.spelling)
            locs.name.add(m.group(1))
        elif field == 'cvarFlags':
            locs.flags.extend(map(str.strip, get_source(value).split('|')))

def f(cur, p=None):
    if cur.type.spelling.endswith('::cvarTable_t') and cur.kind == CursorKind.INIT_LIST_EXPR:
        handle_table(cur)
    if re.search(r'\b(cvar_t|vmCvar_t)\b', cur.type.spelling):
        if not cur.location.file:
            print('wat', cur.kind, cur.type.spelling)
            print(' '.join(t.spelling for t in cur.get_tokens()))
        if cur.kind == CursorKind.TYPE_REF:
            pass # uninteresting
        elif cur.kind == CursorKind.VAR_DECL and cur.linkage != cindex.LinkageKind.NO_LINKAGE:
            # NO_LINKAGE is local variables, don't want them
            locs = locmap[cur.spelling]
            (locs.defs if cur.is_definition() else locs.fw_decls).add(my_loc(cur))
        elif handle_reference(cur, p):
            pass
        elif handle_unary(cur):
            return
        # Things not about a *specific* cvar
        elif cur.kind in (CursorKind.FUNCTION_DECL, CursorKind.PARM_DECL, CursorKind.STRUCT_DECL, CursorKind.CALL_EXPR):
            pass
        else:
            print('Unhandled thingy', cur.kind, get_file(cur.location.file.name)[cur.location.line-1])

    for child in cur.get_children():
        f(child, cur)

def clangcl_bad(a):
    return a in ('-TP', '/MP') or a.startswith('/F')

# These happen with args being only ['--driver-mode=cl']
BOGUS_DIAGNOSTICS = [
    "warning: unknown argument ignored in clang-cl: '-fno-spell-checking' [-Wunknown-argument]",
    "warning: unknown argument ignored in clang-cl: '-fallow-editor-placeholders' [-Wunknown-argument]",
]

# Choose one arbitrarily when the same file is compiled more than once
files = {command.filename.replace('\\', '/'): command for command in cdb.getAllCompileCommands()}
files = {f: files[f] for f in files if 'libs/' not in f}

# Some generated directories have relative paths in the command line include dirs
os.chdir(argv.b)

def compile_tu(src, args):
    try:
        return index.parse(src, args)
    except cindex.TranslationUnitLoadError as e:
        print(e)
        print('Original command line:', list(command.arguments))
        print('Modified args:', args)
        os._exit(1)

executor = futures.ThreadPoolExecutor(argv.j)
tus = []
for src, command in files.items():
    if argv.f not in src:
        continue
    args = list(command.arguments)
    if args[0].endswith('rc.exe'):
        continue
    del args[0]
    del args[args.index('-c'):]
    args = [a for a in args if not clangcl_bad(a)]
    tus.append(executor.submit(compile_tu, src, args))
futures.wait(tus)

for tu in tus:
    tu = tu.result()
    for d in tu.diagnostics:
        d = str(d)
        if d not in BOGUS_DIAGNOSTICS:
            print(d)
    f(tu.cursor)

def all_sources(srcs):
    src_dirs = set()
    for f in srcs:
        root = f[:f.rindex('src/')]
        src_dirs.add(root + 'src')
        if os.path.exists(root + 'pkg'):
            src_dirs.add(root + 'pkg/unvanquished_src.dpkdir/ui')
    all_srcs = []
    for d in src_dirs:
        for path, _, filenames in os.walk(d):
            for f in filenames:
                if os.path.splitext(f)[1] in ('.h', '.cpp', '.rml', '.lua'):
                    all_srcs.append(path.replace('\\', '/') + '/' + f)
    assert len(all_srcs) == len(set(all_srcs))
    return all_srcs

WORD = re.compile(r'\b\w+\b')
all_srcs = all_sources(files)

if argv.T:
    locmap_text = {var.lower(): locs for var, locs in locmap.items()}
    assert len(locmap_text) == len(locmap)
    for locs in locmap.values():
        for name in map(str.lower, locs.name):
            if name not in locmap_text:
                locmap_text[name] = locs
    for src in all_srcs:
        for n, line in enumerate(get_file(src)):
            for m in re.finditer(WORD, line):
                locs = locmap_text.get(m.group(0).lower())
                if locs:
                    loc = (src, n + 1, m.start() + 1)
                    if not any(loc in g for g in locs.groups()):
                        locs.text.add(loc)

class Patch:
    def __init__(self):
        self.files = {}
        self.context = 3

    def whitespace_around(self, text, i):
        c = 0
        while 0 < i-c and i+c < len(text)-1 and '' == text[i-c-1].strip() == text[i+c+1].strip():
            c += 1
        return c

    def disk_text(self, f):
        return get_file(f, cache=not argv.p)[:]

    def kill_line(self, f, orig_line):
        orig_text = get_file(f)
        if f not in self.files:
            self.files[f] = self.disk_text(f)[:]
        text = self.files[f]
        content = orig_text[orig_line - 1]
        i = text.index(content)
        if text.count(content) > 1:
            print(f'Warning: found multiple lines matching {repr(content)}, deleting one at random')
        del text[i:i + 1 + self.whitespace_around(text, i)]

    def color_diff_line(self, line):
        if line.startswith('+++') or line.startswith('---'):
            return colorama.Style.BRIGHT + line + colorama.Style.NORMAL
        if line.startswith('+'):
            return colorama.Fore.GREEN + line + colorama.Fore.RESET
        if line.startswith('-'):
            return colorama.Fore.RED + line + colorama.Fore.RESET
        if line.startswith('@'):
            return colorama.Fore.CYAN + line + colorama.Fore.RESET
        return line

    def show(self, file=None):
        for f, text in self.files.items():
            for line in difflib.unified_diff(self.disk_text(f), text, f, f, n=self.context, lineterm=''):
                if not file:
                    line = self.color_diff_line(line)
                print(line, file=file)

    def apply(self, edit):
        tf = tempfile.NamedTemporaryFile('w', delete=False, encoding='utf8')
        try:
            self.show(file=tf)
            tf.close()
            if edit:
                subprocess.check_call([editor, tf.name])
            subprocess.check_call(['git', 'apply', '-p0', '--unsafe-paths', tf.name])
        finally:
            tf.close()
            os.unlink(tf.name)

def apply_patch(patch):
    Y = colorama.Fore.YELLOW
    R = colorama.Fore.RESET
    while True:
        patch.show()
        print(f'{Y}Apply patch?{R} [{Y}y{R}es, {Y}n{R}o, {Y}c{R}ontext++, {Y}e{R}dit]')
        choice = input().lower()
        if choice in ('e', 'y'):
            try:
                patch.apply(choice == 'e')
                return
            except subprocess.CalledProcessError:
                pass
        elif choice == 'n':
            return
        elif choice == 'c':
            patch.context += 1

def check_usage(locs):
    if not locs.defs:
        print('UU: no def')
    elif locs.int or locs.float or locs.string or locs.other:
        return True
    elif 'CVAR_USERINFO' in locs.flags and any('src/sgame/' in f for f,_,_ in locs.text):
        return True
    elif locs.text:
        print('UU: probably')
    else:
        print('UU: yes')
    return False

def kill_cvar(locs):
    patch = Patch()
    lines = {loc[:2] for g in locs.allgroups() for loc in g}
    for f, line in lines:
        patch.kill_line(f, line)
    if argv.p:
        apply_patch(patch)
    else:
        patch.show()

os.chdir('/') # so I can use absolute paths in patches

for name, locs in locmap.items():
    if not name.lower().startswith(argv.v):
        continue
    include = False
    for g in locs.groups():
        for f, _, _ in g:
            assert f in all_srcs, f
            include = include or f.endswith('.cpp')
    if not include:
        continue
    locs.table_del()
    print(name, *(f'"{n}"' for n in locs.name))
    def P(tag):
        f, _, col = loc
        print(f"{f}:{col}", tag, locline(loc))
    for loc in locs.fw_decls:
        P('DECL')
    for loc in locs.defs:
        P('DEF ')
    for loc in locs.int:
        P('INT ')
    for loc in locs.float:
        P('FLT ')
    for loc in locs.string:
        P('STR ')
    for loc in locs.table:
        P('TAB ')
    for loc in locs.other:
        P('OTHER')
    for loc in locs.text:
        P('TEXT')
    if not check_usage(locs):
        kill_cvar(locs)
    print()
