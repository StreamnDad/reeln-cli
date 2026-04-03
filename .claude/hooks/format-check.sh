#!/bin/bash
file="$CLAUDE_FILE_PATH"
if [ -n "$file" ] && echo "$file" | grep -q '\.py$'; then
    cd /Users/jremitz/workspace/reeln-cli
    .venv/bin/ruff format "$file" 2>/dev/null
    .venv/bin/ruff check --fix "$file" 2>/dev/null
    remaining=$(.venv/bin/ruff check "$file" 2>&1 | grep -v '^All checks passed')
    if [ -n "$remaining" ]; then
        echo "LINT ISSUES (fix before commit):" >&2
        echo "$remaining" >&2
    fi
fi
exit 0
