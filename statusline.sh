#!/bin/bash
# Claude Code statusLine: 누적 토큰·캐시적중·추정비용·턴을 한 줄로 표시.
# Claude Code가 stdin으로 JSON(transcript_path 등)을 넘겨준다 → measure.py 재활용.
exec python3 "$(dirname "$0")/measure.py" --statusline
