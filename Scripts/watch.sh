#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source patch.sh

if ! version_info="$(main check 2>/dev/null)"; then exit 0; fi
app="$(find_app)"
root="$HOME/Library/Application Support/NoAdTalk"
state="$root/last-notified"
[[ ! -L "$root" && ! -L "$state" ]] || exit 1
fingerprint="$version_info $(digest "$app/Contents/Resources/FSMainViewController.nib")"
if [[ -f "$state" && "$(cat "$state")" == "$fingerprint" ]]; then exit 0; fi
umask 077
mkdir -p "$root"
printf '%s\n' "$fingerprint" > "$state"
choice="$(/usr/bin/osascript - "$version_info" <<'APPLESCRIPT'
on run argv
    set result to display dialog "카카오톡 " & item 1 of argv & "에서 광고 숨김을 적용할 수 있습니다. 적용하면 카카오톡을 다시 열며 관리자 인증이 필요할 수 있습니다." buttons {"닫기", "적용"} default button "닫기" giving up after 60
    if gave up of result then return "닫기"
    return button returned of result
end run
APPLESCRIPT
)"
[[ "$choice" == '적용' ]] || exit 0
/usr/bin/osascript - "$root/Agent/NoAdTalk.command" <<'APPLESCRIPT'
on run argv
    tell application "Terminal"
        activate
        do script "/bin/bash " & quoted form of (item 1 of argv) & " apply"
    end tell
end run
APPLESCRIPT
