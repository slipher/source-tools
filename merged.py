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
    _, feature, base = sys.argv
    CheckMerged(feature, base)
