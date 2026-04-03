#!/bin/bash
cd /Users/jremitz/workspace/reeln-cli
result=$(.venv/bin/ruff check reeln/ tests/ 2>&1 | grep -v '^All checks passed')
if [ -n "$result" ]; then
    echo "LINT FAILURES - fix before committing:" >&2
    echo "$result" >&2
    exit 1
fi
exit 0
