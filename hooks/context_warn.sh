#!/bin/bash
# UserPromptSubmit hook: 컨텍스트 비대·낮은 캐시적중일 때만 경고 한 줄 출력.
# stdout는 Claude 컨텍스트에 주입되어 넛지로 작동한다(넘지 않으면 아무것도 안 냄).
exec python3 "$(dirname "$0")/../measure.py" --check
