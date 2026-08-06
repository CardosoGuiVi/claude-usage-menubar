#!/usr/bin/env bash
# Runs after Claude edits/writes a file. Enforces Principle III in real
# time, during the session, before anything even reaches a commit or CI.
#
# NOTE: exit 2 on PostToolUse does NOT undo the edit — it already
# happened by the time this hook runs. Exit 2 feeds this script's
# stderr back to Claude as an error message, prompting it to
# self-correct on its next turn. This is a self-correction loop, not a
# hard pre-write block (that would require PreToolUse, which can't
# lint content that doesn't exist yet at that point in the lifecycle).

set -euo pipefail

# Hook receives JSON on stdin describing the tool call; extract the
# file path that was just edited/written.
FILE_PATH=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input', {}).get('file_path', ''))")

# Only care about Python files.
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

echo "Running ruff on $FILE_PATH..." >&2

if ! ruff check "$FILE_PATH"; then
  echo "Ruff found issues in $FILE_PATH — please fix them now." >&2
  exit 2
fi

exit 0