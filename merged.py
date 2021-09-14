#!/usr/bin/env python3

import subprocess
import sys

MAX_COMMITS = 30

def CommitsBetween(feature_branch, base_branch):
    output = subprocess.check_output(
        ['git', 'log', '--format=%s', '-%d' % (MAX_COMMITS + 1), base_branch + '..' + feature_branch])
    onelines = output.splitlines()
    if len(onelines) > MAX_COMMITS:
        exit('more than %d commits found. Wrong base branch?' % MAX_COMMITS)
    return onelines[::-1]

def SearchCommits(commits, branch):
    not_found = set(commits)
    assert len(not_found) == len(commits)
    found = [None] * len(commits)
    branch_onelines = subprocess.check_output(['git', 'log', '--format=%s', branch]).splitlines()
    for i, message in enumerate(branch_onelines):
        if message in not_found:
            found[commits.index(message)] = i
            not_found.remove(message)
    return found

def CheckMerged(feature_branch, base_branch):
    commits = CommitsBetween(feature_branch, base_branch)
    indices = SearchCommits(commits, base_branch)
    for message, index in zip(commits, indices):
        where = 'not found' if index is None else '~%d' % index
        print('%-12s %s' % (where, message))

if __name__ == '__main__':
    if len(sys.argv) == 2:
        base = 'origin/master'
    elif len(sys.argv) == 3:
        base = sys.argv[2]
    else:
        exit('Usage: merged.py <feature branch> [<base branch>]\n\n'
             'Checks whether differing commits on <feature branch> have been rebased\n'
             'onto <base branch> (default: origin/master) using the heuristic of one-line\n'
             'summary comparison')
    feature = sys.argv[1]
    CheckMerged(feature, base)