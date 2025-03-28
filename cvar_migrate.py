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
import traceback

import colorama
from clang import cindex
from clang.cindex import CursorKind

Y = colorama.Fore.YELLOW
R = colorama.Fore.RESET

sys.stdout.reconfigure(encoding='utf-8')
colorama.init()

parser = argparse.ArgumentParser()
parser.add_argument('-b', type=str, help='build directory (with comp db)', default='C:/unv/st/spm')
parser.add_argument('-f', type=str, help='substring to match translation unit filename', default='')
parser.add_argument('-j', type=int, help='compiler threads', default=6)
parser.add_argument('-v', type=str, help='substring for cvars to match', default='')
parser.add_argument('-T', action='store_false', help='disable text matches')
parser.add_argument('-p', action='store_true', help='interactively apply patches')
parser.add_argument('-m', action='store_true', help='migrate cvar instead of deleting unused')
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
        self.gets = set()
        self.int = set()
        self.float = set()
        self.string = set()
        self.cvarsets = set()
        self.assertrange = set()
        self.other = set()

        self.name = set()
        self.flags = []
        self.limits = []
        self.default = set()

    def groups(self): # excluding text
        return [self.fw_decls, self.defs, self.gets, self.int, self.float, self.string, self.cvarsets, self.other]

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

def handle_reference(cur, p, pp):
    if cur.kind != CursorKind.DECL_REF_EXPR:
        return False
    if p.kind == CursorKind.MEMBER_REF_EXPR:
        member = p.referenced
    elif pp.kind == CursorKind.MEMBER_REF_EXPR:
        member = pp.referenced
    else:
        return False

    if cur.get_definition() and cur.get_definition().linkage == cindex.LinkageKind.NO_LINKAGE:
        return False

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
        elif field == 'defaultString':
            locs.default.add(get_source(value))

def get_kind(cur):
    try:
        return cur.kind
    except ValueError:
        return None

cvarsets = collections.defaultdict(set)

def handle_call_expr(cur):
    if cur.kind != CursorKind.CALL_EXPR:
        return False
    try:
        func, *args = cur.get_children()
    except ValueError:
        return False
    if func.spelling in ('trap_Cvar_Set', 'Cvar_Set'):
        var, val = args
        if var.kind == CursorKind.UNEXPOSED_EXPR:
            var = next(iter(var.get_children()))
        if var.kind != CursorKind.STRING_LITERAL:
            return False
        loc = list(my_loc(var))
        loc[2] += 1
        cvarsets[get_source(var).strip('"').lower()].add((tuple(loc), get_source(val)))
        return True
    elif func.spelling == 'AssertCvarRange':
        cv, lower, upper, _ = args
        locs = locmap[cv.spelling]
        locs.limits.append((get_source(lower), get_source(upper)))
        locs.assertrange.add(my_loc(cur))
        return True
    else:
        return False

def handle_cvar_get(cur):
    if cur.kind != CursorKind.BINARY_OPERATOR:
        return False
    left, right = cur.get_children()
    if left.kind != CursorKind.DECL_REF_EXPR or left.type.spelling != 'cvar_t *':
        return False
    if right.kind != CursorKind.CALL_EXPR:
        return False
    func, *args = right.get_children()
    if func.spelling != 'Cvar_Get':
        return False
    name, default, flags = args
    locs = locmap[left.spelling]
    m = re.match(r'^"([a-z]\w*)"$', get_source(name))
    locs.name.add(m.group(1))
    locs.default.add(get_source(default))
    locs.flags.extend(map(str.strip, get_source(flags).split('|')))
    locs.gets.add(my_loc(cur))
    return True

def f(cur, p=None, pp=None):
    if handle_cvar_get(cur):
        return
    if handle_call_expr(cur):
        return
    if cur.type.spelling.endswith('::cvarTable_t') and cur.kind == CursorKind.INIT_LIST_EXPR:
        handle_table(cur)
    if get_kind(cur) == CursorKind.CALL_EXPR:
        try:
            func_tokens = list(next(iter(cur.get_children())).get_tokens())
        except StopIteration:
            pass
        else:
            if len(func_tokens) == 1 and func_tokens[0].spelling == 'trap_Cvar_Set':
                handle_cvar_set(cur)
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
        elif handle_reference(cur, p, pp):
            pass
        elif handle_unary(cur):
            return
        # Things not about a *specific* cvar
        elif cur.kind in (CursorKind.FUNCTION_DECL, CursorKind.PARM_DECL, CursorKind.STRUCT_DECL, CursorKind.CALL_EXPR):
            pass
        elif cur.kind == CursorKind.UNEXPOSED_EXPR:
            pass # some annoying expression containing the name of a pointer to cvar
        else:
            print('Unhandled thingy', cur.kind, cur.spelling, get_file(cur.location.file.name)[cur.location.line-1])

    for child in cur.get_children():
        f(child, cur, p)

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
        if 'DaemonBuildInfo' in f:
            continue
        root = f[:f.rindex('src/')]
        src_dirs.add(root + 'src')
        if (not argv.m) and os.path.exists(root + 'pkg'):
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


locmap_text = {var.lower(): locs for var, locs in locmap.items()}
assert len(locmap_text) == len(locmap)
for locs in locmap.values():
    for name in map(str.lower, locs.name):
        if name not in locmap_text:
            locmap_text[name] = locs
for name, locs in locmap_text.items():
    for loc, _ in cvarsets[name]:
        locs.cvarsets.add(loc)
if argv.T:
    for src in all_srcs:
        for n, line in enumerate(get_file(src)):
            for m in re.finditer(WORD, line):
                locs = locmap_text.get(m.group(0).lower())
                if locs:
                    loc = (src, n + 1, m.start() + 1)
                    if not any(l[:2] == loc[:2] for g in locs.groups() for l in g):
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

    def find_line(self, f, orig_line):
        orig_text = get_file(f)
        if f not in self.files:
            self.files[f] = self.disk_text(f)[:]
        text = self.files[f]
        content = orig_text[orig_line - 1]
        try:
            i = text.index(content)
        except ValueError:
            return None
        if text.count(content) > 1:
            print(f'Warning: found multiple lines matching {repr(content)}, deleting one at random')
        return i

    def kill_line(self, f, orig_line):
        i = self.find_line(f, orig_line)
        if i is None:
            print('Warning: failed to delete line ' + repr(orig_line))
            return
        text = self.files[f]
        del text[i:i + 1 + self.whitespace_around(text, i)]

    def replace_line(self, f, orig_line, replacement):
        i = self.find_line(f, orig_line)
        if i is None:
            print('Warning: failed to replace line ' + repr(orig_line))
            return
        self.files[f][i] = replacement

    def mark_line(self, f, orig_line):
        i = self.find_line(f, orig_line)
        if i is None:
            print('Warning: failed to mark line ' + repr(orig_line))
            return
        self.files[f][i] = '\uBEEF' + self.files[f][i]

    def color_diff_line(self, line):
        if line.startswith('+++') or line.startswith('---'):
            return colorama.Style.BRIGHT + line + colorama.Style.NORMAL
        if line.startswith('+'):
            return colorama.Fore.GREEN + line + colorama.Fore.RESET
        if line.startswith('-'):
            return colorama.Fore.RED + line + colorama.Fore.RESET
        if line.startswith('@'):
            return colorama.Fore.CYAN + line + colorama.Fore.RESET
        if line.startswith('*'):
            return colorama.Style.BRIGHT + line + colorama.Style.NORMAL
        return line

    def show(self, file=None):
        for f, text in self.files.items():
            diff = list(difflib.unified_diff(self.disk_text(f), text, f, f, n=self.context, lineterm=''))
            i = 0
            while i < len(diff):
                line = diff[i]
                if line.startswith('-'):
                    beef = '+\uBEEF' + line[1:]
                    if beef in diff[i+1:i+9]:
                        line = '*' + line[1:]
                        del diff[diff.index(beef, i+1)]
                if not file:
                    line = self.color_diff_line(line)
                print(line, file=file)
                i += 1

    def apply(self, edit):
        tf = tempfile.NamedTemporaryFile('w', delete=False, encoding='utf8')
        try:
            self.show(file=tf)
            tf.close()
            cmd = ['git', 'apply', '-p0', '--unsafe-paths', tf.name]
            if not edit:
                subprocess.check_call(cmd)
                return
            while True:
                try:
                    subprocess.check_call([editor, tf.name])
                finally:
                    # BLACK MAGIC: on Windows 10 colorama stops working after executing Vim;
                    # it just prints out the ANSI codes unmodified. But doing this makes it work again
                    os.system('color')
                try:
                    subprocess.check_call(['git', 'apply', '-p0', '--unsafe-paths', tf.name])
                except subprocess.CalledProcessError:
                    while True:
                        print(f'Re-edit failed patch? [{Y}y{R}es, {Y}n{R}o]')
                        choice = input().lower()
                        if choice == 'y':
                            break
                        elif choice == 'n':
                            raise
                else:
                    return
        finally:
            tf.close()
            os.unlink(tf.name)

def apply_patch(patch):
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
    elif 'CVAR_SERVERINFO' in locs.flags or 'CVAR_ROM' in locs.flags:
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

def translate_flags(flags):
    FLAGS = {
        '0': 'Cvar::NONE',
        'CVAR_CHEAT': 'Cvar::CHEAT',
        'CVAR_USERINFO': 'Cvar::USERINFO',
        'CVAR_ROM': 'Cvar::ROM',
        'CVAR_SERVERINFO': 'Cvar::SERVERINFO',
        'CVAR_SYSTEMINFO': 'Cvar::SYSTEMINFO',
    }
    return ' | '.join(FLAGS.get(flag, f'<CVARTODO: {flag}>')
                      for flag in flags
                      if flag != 'CVAR_LATCH') or 'Cvar::NONE'

# g_foo.x, locs.x, Cvar<x>
FLOAT = 'value', 'float', 'Cvar<float>'
FLOATRANGE = 'value', 'float', 'Range<Cvar::Cvar<float>>'
INT = 'integer', 'int', 'Cvar<int>'
INTRANGE = 'integer', 'int', 'Range<Cvar::Cvar<int>>'
BOOL = 'integer', 'int', 'Cvar<bool>'
STRING = 'string', 'string', 'Cvar<std::string>'

def guess_type(locs):
    lim = locs.limits[0] if locs.limits else ()
    if locs.float:
        return (FLOATRANGE if locs.limits else FLOAT), lim
    if locs.int:
        return (INTRANGE if locs.limits else INT), lim
    return STRING, ()

def destringize(val, type):
    if type is not STRING:
        val = val.strip('"')
        if type is BOOL:
            val = str(bool(int(val))).lower()
    return val

def migration_patch(name, locs, type, desc, limits):
    accessor, grp, newtype = type
    group = getattr(locs, grp)
    patch = Patch()
    for f, line, _ in locs.table:
        patch.kill_line(f, line)
    for f, line, _ in locs.assertrange:
        patch.kill_line(f, line)
    for f, line, _ in locs.fw_decls:
        patch.replace_line(f, line, f'extern Cvar::{newtype} {name};')
    for f, line, _ in locs.defs:
        name2, = locs.name
        default, = locs.default
        default = destringize(default, type)
        for n in limits:
            default += f', {n}'
        defn = f'Cvar::{newtype} {name}("{name2}", "{desc}", {translate_flags(locs.flags)}, {default});'
        patch.replace_line(f, line, defn)
    for f, line, _ in locs.gets:
        if 'CVAR_LATCH' in locs.flags:
            oldtext = get_file(f)[line-1]
            indent = oldtext[:len(oldtext) - len(oldtext.lstrip())]
            patch.replace_line(f, line, f'{indent}Cvar::Latch({name});')
        else:
            patch.kill_line(f, line)
    for (f, line, _), val in cvarsets[name2.lower()]:
        oldtext = get_file(f)[line-1]
        indent = oldtext[:len(oldtext) - len(oldtext.lstrip())]
        if 'CVAR_ROM' in locs.flags:
            patch.replace_line(f, line, f'{indent}Cvar::SetValueForce( "{name}", {val} );')
        else:
            patch.replace_line(f, line, f'{indent}{name2}.Set( {destringize(val, type)} );')
    get_expr = name + '.Get()'
    if type is STRING:
        get_expr += '.c_str()'
    for f, line in {loc[:2] for loc in group}:
        text = get_file(f)[line-1]
        text = text.replace(f'{name}.{accessor}', get_expr)
        text = text.replace(f'{name}->{accessor}', get_expr)
        patch.replace_line(f, line, text)
    handled_groups = (group, locs.fw_decls, locs.defs, locs.table, locs.cvarsets, locs.gets, locs.assertrange)
    lines = {loc[:2] for g in locs.allgroups()
             if not any(g is h for h in handled_groups)
             for loc in g}
    for f, line in lines:
        patch.mark_line(f, line)
    return patch

def read_type():
    while True:
        print(f'Choose cvar type [{Y}f{R}loat, flo{Y}a{R}t range, {Y}i{R}nt, {Y}r{R}ange int, {Y}b{R}ool, {Y}s{R}tring]')
        choice = input().lower()
        if choice == 'f':
            return FLOAT
        if choice == 'a':
            return FLOATRANGE
        if choice == 'i':
            return INT
        if choice == 'r':
            return INTRANGE
        if choice == 'b':
            return BOOL
        if choice == 's':
            return STRING

def migrate_cvar(name, locs):
    type, limits = guess_type(locs)
    if not locs.name or not locs.default:
        print(name + ' is missing stuff')
        return
    patch = migration_patch(name, locs, type, 'CVARTODO:desc', ())
    patch.show()
    if not argv.p:
        return
    while True:
        print(f'migrate {name}? [{Y}y{R}es, {Y}n{R}o, change {Y}t{R}ype]')
        choice = input().lower()
        if choice == 'n':
            return
        elif choice == 'y':
            break
        elif choice == 't':
            type = read_type()
            if type in (INTRANGE, FLOATRANGE):
                limits = input('Min: '), input('Max: ')
            else:
                limits = ()
    desc = input('Description: ')
    try:
        patch = migration_patch(name, locs, type, desc, limits)
        apply_patch(patch)
    except Exception:
        traceback.print_exc()

os.chdir('/') # so I can use absolute paths in patches

for name, locs in locmap.items():
    if argv.v not in name.lower():
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
    for loc in locs.gets:
        P('GET ')
    for loc in locs.int:
        P('INT ')
    for loc in locs.float:
        P('FLT ')
    for loc in locs.string:
        P('STR ')
    for loc in locs.table:
        P('TAB ')
    for loc in locs.cvarsets:
        P('SET ')
    for loc  in locs.assertrange:
        P('RANGE')
    for loc in locs.other:
        P('OTHER')
    for loc in locs.text:
        P('TEXT')
    if argv.m:
        migrate_cvar(name, locs)
    else:
        if not check_usage(locs):
            kill_cvar(locs)
    print()
