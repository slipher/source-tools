#!/usr/bin/env python3

import subprocess
import sys

MAX_COMMITS = 90

def CommitsBetween(feature_branch, base_branch):
    output = subprocess.check_output(
        ['git', 'log', '--format=%s', '-%d' % (MAX_COMMITS + 1), base_branch + '..' + feature_branch])
    onelines = output.splitlines()
    if len(onelines) > MAX_COMMITS:
        exit('more than %d commits found. Wrong base branch?' % MAX_COMMITS)
    return onelines[::-1]

def SearchCommits(commits, branch):
    not_found = set(commits)
    if len(not_found) != len(commits):
        print('Warning: identical commit descriptions found')
    found = [None] * len(commits)
    branch_onelines = subprocess.check_output(['git', 'log', '--format=%s', branch]).splitlines()
    for i, message in enumerate(branch_onelines):
        if message in not_found:
            found[commits.index(message)] = i
            not_found.remove(message)
    return found

def CheckMerged(feature_branch, base_branch, autodelete):
    commits = CommitsBetween(feature_branch, base_branch)
    indices = SearchCommits(commits, base_branch)
    differs = False
    for message, index in zip(commits, indices):
        if index is None:
            differs = True
            where = 'not found'
        else:
            where = '~%d' % index
        print('%-12s %s' % (where, message))
    if autodelete and not differs:
        flag = '-D' if commits else '-d'
        subprocess.check_call(['git', 'branch', flag, feature_branch])

if __name__ == '__main__':
    argv = sys.argv.copy()
    autodelete = '-d' in argv
    if autodelete:
        argv.remove('-d')
    if len(argv) == 2:
        base = 'origin/master'
    elif len(argv) == 3:
        base = argv[2]
    else:
        exit('Usage: merged.py [-d] <feature branch> [<base branch>]\n\n'
             'Checks whether differing commits on <feature branch> have been rebased\n'
             'onto <base branch> (default: origin/master) using the heuristic of one-line\n'
             'summary comparison. -d deletes the branch if there are no differing commits.')
    feature = argv[1]
    CheckMerged(feature, base, autodelete)
