#!/bin/bash
# Stop / SessionEnd hook: 세션 낭비 부검을 출력한다.
# stdin JSON에서 transcript_path를 뽑아 measure.py --autopsy 에 넘긴다.
path=$(python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("transcript_path",""))
except Exception: print("")' 2>/dev/null)
if [ -n "$path" ] && [ -f "$path" ]; then
  python3 "$(dirname "$0")/../measure.py" --autopsy "$path"
  if [ -n "$CLAUDE_PLUGIN_DATA" ]; then
    python3 "$(dirname "$0")/../measure.py" --capture-failures "$path" --data-dir "$CLAUDE_PLUGIN_DATA"
  else
    python3 "$(dirname "$0")/../measure.py" --capture-failures "$path"
  fi
fi
