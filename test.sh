#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source Scripts/patch.sh
PATCHED_SHA="d71a99a9b6ea0a825c6b01a3e12557d9386c3c6b7cba71e5bea92f2d3a4a5651"

test_dir="$(mktemp -d "${TMPDIR:-/tmp}/no-ad-talk-test.XXXXXXXX")"
trap 'rm -rf -- "$test_dir"' EXIT
app="$(find_app)"
original="$app/Contents/Resources/FSMainViewController.nib"
backup="$HOME/Library/Application Support/NoAdTalk/26.9.0-2006/FSMainViewController.nib"
if [[ "$(digest "$original")" != "$ORIGINAL_SHA" && -f "$backup" ]]; then original="$backup"; fi
[[ "$(digest "$original")" == "$ORIGINAL_SHA" ]]

patch_nib "$original" "$test_dir/patched.nib"
[[ "$(digest "$test_dir/patched.nib")" == "$PATCHED_SHA" ]]
printf 'invalid\n' > "$test_dir/invalid.nib"
printf 'unchanged\n' > "$test_dir/untouched.nib"
if patch_nib "$test_dir/invalid.nib" "$test_dir/untouched.nib"; then exit 1; fi
[[ "$(cat "$test_dir/untouched.nib")" == 'unchanged' ]]

cp "$original" "$test_dir/swap.nib"
chmod 640 "$test_dir/swap.nib"
if replace_nib "$test_dir/invalid.nib" "$test_dir/swap.nib" "$ORIGINAL_SHA" "$PATCHED_SHA"; then exit 1; fi
[[ "$(digest "$test_dir/swap.nib")" == "$ORIGINAL_SHA" ]]
if compgen -G "$test_dir/.no-ad-talk.*" >/dev/null; then exit 1; fi
replace_nib "$test_dir/patched.nib" "$test_dir/swap.nib" "$ORIGINAL_SHA" "$PATCHED_SHA"
[[ "$(/usr/bin/stat -f '%Lp' "$test_dir/swap.nib")" == '640' ]]
if replace_nib "$original" "$test_dir/swap.nib" "$ORIGINAL_SHA" "$ORIGINAL_SHA"; then exit 1; fi
[[ "$(digest "$test_dir/swap.nib")" == "$PATCHED_SHA" ]]
replace_nib "$original" "$test_dir/swap.nib" "$PATCHED_SHA" "$ORIGINAL_SHA"
[[ "$(digest "$test_dir/swap.nib")" == "$ORIGINAL_SHA" ]]

/usr/bin/python3 -B tests/test_nib.py "$original" "$test_dir/relocated.nib"

for fixture in original patched relocated; do
    mkdir -p "$test_dir/$fixture.app/Contents/Resources"
    cp "$app/Contents/Info.plist" "$test_dir/$fixture.app/Contents/Info.plist"
done
cp "$original" "$test_dir/original.app/Contents/Resources/FSMainViewController.nib"
cp "$test_dir/patched.nib" "$test_dir/patched.app/Contents/Resources/FSMainViewController.nib"
cp "$test_dir/relocated.nib" "$test_dir/relocated.app/Contents/Resources/FSMainViewController.nib"
/usr/bin/clang -fobjc-arc -Werror -framework Cocoa tests/nib_probe.m -o "$test_dir/nib_probe"
original_layout="$("$test_dir/nib_probe" "$test_dir/original.app" 2>"$test_dir/original.log")" || { cat "$test_dir/original.log" >&2; exit 1; }
patched_layout="$("$test_dir/nib_probe" "$test_dir/patched.app" 2>"$test_dir/patched.log")" || { cat "$test_dir/patched.log" >&2; exit 1; }
[[ "$original_layout" == '100 1 0 487 100 1' ]]
[[ "$patched_layout" == '0 0 1 588 0 0' ]]
[[ "$("$test_dir/nib_probe" "$test_dir/relocated.app" 2>"$test_dir/relocated.log")" == "$patched_layout" ]]

/bin/dd if="$test_dir/patched.nib" of="$test_dir/legacy.nib" bs=1 count=4692 2>/dev/null
printf '\012\023\000\000\000' >> "$test_dir/legacy.nib"
/bin/dd if="$test_dir/patched.nib" bs=1 skip=4693 2>/dev/null >> "$test_dir/legacy.nib"
printf '\360\117\000\000' | /bin/dd of="$test_dir/legacy.nib" bs=1 seek=46 conv=notrunc 2>/dev/null
[[ "$(digest "$test_dir/legacy.nib")" == "$LEGACY_SHA" ]]

fixture="$test_dir/KakaoTalk.app"
cp -cR "$app" "$fixture"
cp "$original" "$fixture/Contents/Resources/FSMainViewController.nib"
/usr/bin/codesign --verify --strict --deep "$fixture"
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    kakao_running() { return 1; }
    quit_app() { was_running=0; }
    main apply
)
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$PATCHED_SHA" ]]
[[ "$(digest "$test_dir/backup/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
if /usr/bin/codesign --verify --strict --deep "$fixture" >/dev/null 2>&1; then exit 1; fi
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    main apply
)
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    kakao_running() { return 1; }
    quit_app() { was_running=0; }
    main restore
)
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
/usr/bin/codesign --verify --strict --deep "$fixture"
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    main restore
)
printf 'invalid\n' > "$test_dir/backup/FSMainViewController.nib"
if (
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    main apply
) 2>"$test_dir/invalid-backup.log"; then exit 1; fi
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
/usr/bin/codesign --verify --strict --deep "$fixture"
cp "$original" "$test_dir/backup/FSMainViewController.nib"
if (
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    kakao_running() { return 1; }
    quit_app() { was_running=1; }
    launch_app() { return 1; }
    open_app() { return 0; }
    main apply
) 2>"$test_dir/rollback.log"; then exit 1; fi
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
/usr/bin/codesign --verify --strict --deep "$fixture"
/usr/bin/grep -q '원본을 복구했습니다' "$test_dir/rollback.log"
cp "$test_dir/legacy.nib" "$fixture/Contents/Resources/FSMainViewController.nib"
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    kakao_running() { return 1; }
    quit_app() { was_running=0; }
    main apply
)
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$PATCHED_SHA" ]]
[[ "$(digest "$test_dir/backup/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
cp "$test_dir/legacy.nib" "$fixture/Contents/Resources/FSMainViewController.nib"
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/backup"; }
    kakao_running() { return 1; }
    quit_app() { was_running=0; }
    main restore
)
/usr/bin/codesign --verify --strict --deep "$fixture"
/usr/libexec/PlistBuddy -c 'Set :CFBundleShortVersionString 27.1.0' "$fixture/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleVersion 3000' "$fixture/Contents/Info.plist"
(
    find_app() { printf '%s\n' "$fixture"; }
    backup_root() { printf '%s\n' "$test_dir/versions/$version-$build"; }
    verify_signature() { return 0; }
    kakao_running() { return 1; }
    quit_app() { was_running=0; }
    (main check)
    [[ ! -d "$test_dir/versions" ]]
    (main apply)
    [[ -f "$test_dir/versions/27.1.0-3000/FSMainViewController.nib" ]]
    if (main check); then exit 1; else [[ "$?" == 3 ]]; fi
    (main restore)
)
[[ "$(digest "$fixture/Contents/Resources/FSMainViewController.nib")" == "$ORIGINAL_SHA" ]]
/usr/bin/python3 -B tests/test_automation.py
/usr/bin/python3 -B tests/test_manage.py
printf '검사 통과\n'
