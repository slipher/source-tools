#!/bin/bash

WSD_FORMAT=${WSD_FORMAT:-clang-format}

if [[ -z $GIT_DIFF_PATH_COUNTER ]]; then
    # GIT_DIFF_PATH_COUNTER not defined: the script acts as a replacement for 'git diff'
    GIT_EXTERNAL_DIFF=$0 exec git diff $*
fi

if [[ $# -ne 7 ]]; then
    echo 'Expected 7 arguments as GIT_EXTERNAL_DIFF tool'
    exit 1
fi

if [[ $4 = . ]]; then
    echo "Created file $1 with mode $7"
    LEFT=/dev/null
    RIGHT=b/$1
elif [[ $7 = . ]]; then
    echo "Deleted file $1"
    LEFT=a/$1
    RIGHT=/dev/null
else
    if [[ $4 != $7 ]]; then
        echo "Mode change $4 -> $7 of $1"
    fi
    LEFT=a/$1
    RIGHT=b/$1
fi

run_diff() {
    diff -u --color=always --strip-trailing-cr --label="$LEFT" --label="$RIGHT" -- "$1" "$2"
}

if [[ $4 != . && ($1 == *.h || $1 == *.c || $1 == *.cpp) ]]; then
    run_diff <("$WSD_FORMAT" "$2") <("$WSD_FORMAT" "$5")
else
    run_diff "$2" "$5"
fi
exit 0 # Ignore exit code of diff
