#!/usr/bin/env python3

import pathlib
import re
import os
import subprocess

DIR = os.path.dirname(__file__)

def TestQuery(name):
    success = True
    def error(msg):
        nonlocal success
        success = False
        print("Error:", msg)
    cpp = os.path.join(DIR, name + ".cpp")
    query = os.path.join(DIR, name + ".query")
    with open(cpp) as content:
        expected = [i+1 for i,ln in enumerate(content) if "//!" in ln]
    out = subprocess.check_output(["clang-query",
                                   "--extra-arg=-fno-diagnostics-color",
                                   "-p", DIR,
                                   "-f", query,
                                   cpp],
                                  text=True)
    path = pathlib.Path(cpp)
    actual = []
    for file, line in re.findall(r'^(.*):(\d+):\d+: note: ".*" binds here', out, re.MULTILINE):
        if pathlib.Path(file) != path:
            error(f"Match in unexpected file {file}:{line}")
        else:
            actual.append(int(line))
    for num in sorted(set(expected + actual)):
        ec = expected.count(num)
        ac = actual.count(num)
        if ec == 1 and ac == 0:
            error(f"No match on line {num}")
        elif ec == 0 and ac == 1:
            error(f"Unexpected match on line {num}")
        elif ac != ec:
            error(f"Expected {ec} match(es) on line {num}, but got {ac}")
    if not success:
        print("Output:")
        print(out)
    return success

TestQuery("glm-indexing-ub")
