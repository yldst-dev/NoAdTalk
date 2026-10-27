#!/bin/bash
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

ORIGINAL_SHA="21842c678fde4ce88583ad7c3b42863e7ac91daba7b5f6d106b06714020257be"
LEGACY_SHA="2fefe25a5e03de0dc3f7b7f1dae46cbd5a0eab53b6bc7ce6003fe5c7e0e2aca7"
use_sudo=0
temporary_dir=""

digest() {
    /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

patch_nib() {
    /usr/bin/python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/nib.py" "$1" "$2"
}

privileged() {
    if [[ "$use_sudo" == 1 ]]; then
        /usr/bin/sudo "$@"
    else
        "$@"
    fi
}

remove_stage() {
    privileged /bin/rm -f "$1" || { printf '임시 파일을 지우지 못했습니다: %s\n' "$1" >&2; return 1; }
}

check_write_access() {
    local probe
    if ! probe="$(LC_ALL=C privileged /usr/bin/mktemp "$(dirname "$1")/.no-ad-talk.XXXXXXXX" 2>"$temporary_dir/write-error")"; then
        cat "$temporary_dir/write-error" >&2
        if /usr/bin/grep -q 'Operation not permitted' "$temporary_dir/write-error"; then
            printf 'macOS가 앱 변경을 차단했습니다. 시스템 설정 → 개인정보 보호 및 보안 → 앱 관리에서 실행 중인 터미널 앱을 허용한 뒤 다시 실행해 주세요.\n' >&2
            return 77
        fi
        return 1
    fi
    remove_stage "$probe"
}

replace_nib() {
    local input="$1" destination="$2" expected_current="$3" expected_new="$4"
    local directory stage mode owner staged_sha
    directory="$(dirname "$destination")"
    [[ -f "$destination" && ! -L "$destination" ]] || return 1
    [[ "$(digest "$destination")" == "$expected_current" ]] || return 1
    mode="$(/usr/bin/stat -f '%Lp' "$destination")" || return 1
    owner="$(/usr/bin/stat -f '%u:%g' "$destination")" || return 1
    stage="$(privileged /usr/bin/mktemp "$directory/.no-ad-talk.XXXXXXXX")" || return 1
    if ! privileged /bin/cp "$input" "$stage" || ! privileged /bin/chmod "$mode" "$stage"; then
        remove_stage "$stage" || true
        return 1
    fi
    if [[ "$use_sudo" == 1 ]] && ! privileged /usr/sbin/chown "$owner" "$stage"; then
        remove_stage "$stage" || true
        return 1
    fi
    if ! staged_sha="$(privileged /usr/bin/shasum -a 256 "$stage" | /usr/bin/awk '{print $1}')"; then
        remove_stage "$stage" || true
        return 1
    fi
    if [[ "$staged_sha" != "$expected_new" || "$(digest "$destination")" != "$expected_current" ]]; then
        remove_stage "$stage" || true
        return 1
    fi
    if ! privileged /bin/mv -f "$stage" "$destination"; then
        remove_stage "$stage" || true
        return 1
    fi
}

find_app() {
    local candidate pid executable
    pid="$(/usr/bin/pgrep -u "$(id -u)" -x KakaoTalk | /usr/bin/head -n 1 || true)"
    if [[ -n "$pid" ]]; then
        executable="$(/bin/ps -p "$pid" -o comm=)" || return 1
        if [[ "$executable" == */Contents/MacOS/KakaoTalk ]]; then
            candidate="${executable%/Contents/MacOS/KakaoTalk}"
            if [[ -f "$candidate/Contents/Info.plist" ]]; then
                printf '%s\n' "$candidate"
                return 0
            fi
        fi
    fi
    for candidate in /Applications/KakaoTalk.app "$HOME/Applications/KakaoTalk.app"; do
        if [[ -f "$candidate/Contents/Info.plist" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

backup_root() {
    printf '%s\n' "$HOME/Library/Application Support/NoAdTalk/$version-$build"
}

verify_signature() {
    /usr/bin/codesign --verify --strict "$@" "$app"
}

kakao_running() {
    /usr/bin/pgrep -u "$(id -u)" -x KakaoTalk >/dev/null
}

quit_app() {
    local pid executable attempt
    was_running=0
    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        executable="$(/bin/ps -p "$pid" -o comm=)" || return 1
        [[ "$executable" == "$app/Contents/MacOS/KakaoTalk" ]] || return 1
        was_running=1
    done < <(/usr/bin/pgrep -u "$(id -u)" -x KakaoTalk || true)
    [[ "$was_running" == 1 ]] || return 0
    printf '카카오톡을 종료한 뒤 다시 엽니다.\n'
    /usr/bin/osascript -e 'tell application id "com.kakao.KakaoTalkMac" to quit' || return 1
    for ((attempt = 0; attempt < 40; attempt++)); do
        if ! kakao_running; then return 0; fi
        sleep 0.25
    done
    return 1
}

open_app() {
    /usr/bin/open -a "$app"
}

launch_app() {
    local attempt
    open_app || return 1
    for ((attempt = 0; attempt < 30; attempt++)); do
        if kakao_running; then
            sleep 2
            kakao_running
            return
        fi
        sleep 0.5
    done
    return 1
}

main() {
    local action="${1:-}" app_info team nib current backup_dir backup new_file
    local version build original_sha patched_sha already_patched=0
    [[ "$action" == apply || "$action" == restore || "$action" == check ]] || { printf '실행 방법을 확인해 주세요.\n' >&2; return 1; }
    app="$(find_app)" || { printf '카카오톡 앱을 찾지 못했습니다.\n' >&2; return 1; }
    app_info="$app/Contents/Info.plist"
    nib="$app/Contents/Resources/FSMainViewController.nib"
    [[ -f "$nib" && ! -L "$nib" ]] || { printf '화면 파일을 찾지 못했습니다.\n' >&2; return 1; }
    [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app_info")" == 'com.kakao.KakaoTalkMac' ]] || return 1
    version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app_info")" || return 1
    build="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app_info")" || return 1
    [[ "$version" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && "$build" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { printf '앱 버전 표기가 올바르지 않습니다.\n' >&2; return 1; }
    team="$(/usr/bin/codesign -dv --verbose=2 "$app" 2>&1 | /usr/bin/grep '^TeamIdentifier=' || true)"
    [[ "$team" == 'TeamIdentifier=L75WVXX68A' ]] || { printf '카카오톡 서명 정보를 확인하지 못했습니다.\n' >&2; return 1; }
    verify_signature --ignore-resources || { printf '실행 파일의 서명이 유효하지 않습니다.\n' >&2; return 1; }
    current="$(digest "$nib")" || return 1
    backup_dir="$(backup_root)"
    backup="$backup_dir/FSMainViewController.nib"
    [[ ! -L "$backup_dir" && ! -L "$backup" ]] || { printf '백업 경로에 심볼릭 링크를 사용할 수 없습니다.\n' >&2; return 1; }
    temporary_dir="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/no-ad-talk.XXXXXXXX")" || return 1
    trap '[[ -z "$temporary_dir" ]] || rm -r -- "$temporary_dir"' EXIT
    new_file="$temporary_dir/patched.nib"

    if [[ -e "$backup" ]]; then
        [[ -f "$backup" ]] || return 1
        patch_nib "$backup" "$new_file" || { printf '원본 백업을 분석하지 못했습니다.\n' >&2; return 1; }
        original_sha="$(digest "$backup")" || return 1
        patched_sha="$(digest "$new_file")" || return 1
        if [[ "$current" == "$patched_sha" ]]; then
            already_patched=1
        elif [[ "$current" == "$LEGACY_SHA" && "$original_sha" == "$ORIGINAL_SHA" ]]; then
            :
        elif [[ "$current" != "$original_sha" ]]; then
            printf '설치된 화면 파일과 이 버전의 백업이 맞지 않아 중단했습니다.\n' >&2
            return 1
        fi
    else
        verify_signature --deep || { printf '원본 서명을 확인하지 못했습니다. 복구 가능한 백업도 없습니다.\n' >&2; return 1; }
        if [[ "$action" == restore ]]; then printf '이미 원래 상태입니다.\n'; return 0; fi
        patch_nib "$nib" "$new_file" || return 1
        original_sha="$current"
        patched_sha="$(digest "$new_file")" || return 1
    fi

    if [[ "$action" != restore && "$already_patched" == 1 ]]; then
        if [[ "$action" == check ]]; then return 3; fi
        printf '광고 숨김이 이미 적용되어 있습니다.\n'
        return 0
    fi
    if [[ "$current" == "$original_sha" ]]; then
        verify_signature --deep || return 1
        if [[ "$action" == restore ]]; then printf '이미 원래 상태입니다.\n'; return 0; fi
    fi
    if [[ "$action" == check ]]; then printf '%s %s\n' "$version" "$build"; return 0; fi

    if [[ "$action" == apply && ! -e "$backup" ]]; then
        umask 077
        mkdir -p "$backup_dir" || return 1
        cp "$nib" "$temporary_dir/backup" || return 1
        [[ "$(digest "$temporary_dir/backup")" == "$original_sha" ]] || return 1
        /bin/ln "$temporary_dir/backup" "$backup" 2>/dev/null || /bin/cp -n "$temporary_dir/backup" "$backup" || return 1
        [[ -f "$backup" && ! -L "$backup" && "$(digest "$backup")" == "$original_sha" ]] || return 1
    fi
    if [[ "$action" == restore ]]; then new_file="$backup"; fi
    if [[ ! -w "$nib" || ! -w "$(dirname "$nib")" ]]; then
        printf '변경을 위해 macOS 관리자 암호가 필요합니다. 암호는 화면에 표시되지 않습니다.\n'
        /usr/bin/sudo -v || return 1
        use_sudo=1
    fi
    check_write_access "$nib" || return $?
    if kakao_running; then
        /usr/bin/osascript -e 'display dialog "카카오톡을 종료하고 다시 열어야 합니다. 저장하지 않은 내용이 있다면 먼저 저장해 주세요." buttons {"취소", "계속"} default button "계속" cancel button "취소"' >/dev/null || return 1
    fi
    [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app_info")" == "$version" && "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$app_info")" == "$build" ]] || { printf '작업 중 앱 버전이 바뀌어 중단했습니다.\n' >&2; return 1; }
    quit_app || { printf '카카오톡을 종료하지 못해 변경하지 않았습니다.\n' >&2; return 1; }
    local expected_new="$patched_sha"
    if [[ "$action" == restore ]]; then expected_new="$original_sha"; fi
    if ! replace_nib "$new_file" "$nib" "$current" "$expected_new"; then
        if [[ "$was_running" == 1 ]]; then open_app || true; fi
        printf '파일 변경에 실패했습니다.\n' >&2
        return 1
    fi
    if [[ "$was_running" == 1 ]] && ! launch_app; then
        if [[ "$action" == apply ]] && replace_nib "$backup" "$nib" "$patched_sha" "$original_sha"; then
            open_app || true
            printf '카카오톡이 열리지 않아 원본을 복구했습니다.\n' >&2
        else
            printf '카카오톡을 열지 못했습니다. 원본 백업과 앱 상태를 확인해 주세요.\n' >&2
        fi
        return 1
    fi
    if [[ "$action" == apply ]]; then
        printf '광고 숨김을 적용했습니다. 화면에서 결과를 확인해 주세요. 원본: %s\n' "$backup"
    else
        verify_signature --deep || { printf '화면은 복구했지만 앱 전체 서명 검사는 실패했습니다.\n' >&2; return 1; }
        printf '카카오톡의 원래 화면을 복구했습니다.\n'
    fi
}

if [[ "${BASH_SOURCE[0]:-}" == "$0" ]]; then
    main "$@"
fi
