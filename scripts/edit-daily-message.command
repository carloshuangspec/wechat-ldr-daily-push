#!/bin/zsh
cd "$(dirname "$0")/.." || exit 1
python3 scripts/edit_daily_message.py
result=$?
printf '\nPress Return to close this window...'
read -r
exit "$result"
