import os
import subprocess
import sys
from pathlib import Path

from automation import LABEL, configure


SCRIPTS = Path(__file__).resolve().parent
ACTIONS = {
    '적용 및 자동 감지 켜기': 'setup',
    '광고 숨김만 적용': 'apply',
    '원래 화면 복구 및 자동 감지 끄기': 'restore',
    '자동 감지만 켜기': 'enable',
    '자동 감지만 끄기': 'disable',
    '상태 확인': 'status',
}


def status():
    result = subprocess.run(['/bin/bash', str(SCRIPTS / 'patch.sh'), 'check'], capture_output=True, text=True)
    if result.returncode == 3:
        patch_status = '광고 숨김: 적용됨'
    elif result.returncode == 0:
        patch_status = '광고 숨김: 적용 가능'
    else:
        reason = (result.stderr or result.stdout).strip()[-600:]
        patch_status = '광고 숨김: 확인 필요' + ('\n' + reason if reason else '')
    watcher = subprocess.run(['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return patch_status + '\n자동 감지: ' + ('켜짐' if watcher.returncode == 0 else '꺼짐')


def run_action(action):
    if action in ('setup', 'apply', 'restore'):
        try:
            subprocess.run(['/bin/bash', str(SCRIPTS / 'patch.sh'), 'restore' if action == 'restore' else 'apply'], check=True)
        except subprocess.CalledProcessError as error:
            if error.returncode != 77:
                raise
            subprocess.run(['/usr/bin/open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_AppBundles'], check=False)
            raise ValueError('macOS가 앱 변경을 차단했습니다. 시스템 설정 → 개인정보 보호 및 보안 → 앱 관리에서 실행 중인 터미널 앱을 허용해 주세요. 터미널을 다시 열라는 안내가 나오면 진행한 뒤 같은 작업을 다시 실행해 주세요. 카카오톡은 종료하거나 변경하지 않았습니다.') from error
    if action in ('setup', 'enable'):
        configure('install')
    elif action in ('restore', 'disable'):
        configure('remove')
    elif action not in ('apply', 'status'):
        raise ValueError('지원하지 않는 관리 작업입니다.')


def dialog(message):
    subprocess.run(['/usr/bin/osascript', '-e', 'on run argv\ndisplay dialog (item 1 of argv) with title "NoAdTalk" buttons {"확인"} default button "확인"\nend run', message], check=True)


def main():
    interactive = len(sys.argv) == 1
    if interactive:
        script = '''on run argv
set options to items 2 thru -1 of argv
with timeout of 3600 seconds
set chosenItems to choose from list options with title "NoAdTalk" with prompt (item 1 of argv) default items {item 1 of options} OK button name "실행" cancel button name "닫기"
end timeout
if chosenItems is false then return ""
return item 1 of chosenItems
end run'''
        result = subprocess.run(['/usr/bin/osascript', '-e', script, status(), *ACTIONS], capture_output=True, text=True, check=True)
        choice = result.stdout.strip()
        if not choice:
            return
        action = ACTIONS[choice]
    elif len(sys.argv) == 2 and sys.argv[1] in ACTIONS.values():
        action = sys.argv[1]
    else:
        raise ValueError('실행 방법을 확인해 주세요.')
    if action == 'status':
        message = status()
    else:
        run_action(action)
        message = '작업을 완료했습니다. 적용한 경우 카카오톡 화면에서 결과를 확인해 주세요.'
    print(message)
    if interactive:
        dialog(message)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or '').strip()
        else:
            detail = str(error)
        message = '작업을 완료하지 못했습니다. 터미널에 표시된 오류를 확인해 주세요.'
        if detail:
            message += '\n' + detail
        print(message, file=sys.stderr)
        if len(sys.argv) == 1:
            try:
                dialog(message)
            except (OSError, subprocess.CalledProcessError):
                pass
        sys.exit(1)
