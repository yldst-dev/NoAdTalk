import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


LABEL = 'local.no-ad-talk.watcher'


def configure(action):
    root = Path.home() / 'Library/Application Support/NoAdTalk'
    agent = root / 'Agent'
    agents = Path.home() / 'Library/LaunchAgents'
    plist = agents / (LABEL + '.plist')
    if any(path.is_symlink() for path in (root, agent, agents, plist)):
        raise ValueError('자동 감지 경로에 심볼릭 링크를 사용할 수 없습니다.')
    domain = 'gui/' + str(os.getuid())
    if action == 'remove':
        subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if plist.exists():
            plist.unlink()
        if agent.exists():
            shutil.rmtree(agent)
        print('업데이트 감지를 해제했습니다. 광고 숨김과 원본 백업은 유지됩니다.')
        return
    source = Path(__file__).resolve().parent.parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    agent.mkdir(exist_ok=True, mode=0o700)
    agents.mkdir(parents=True, exist_ok=True)
    subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if source != agent:
        for name in ('NoAdTalk.command',):
            destination = agent / name
            if destination.is_symlink():
                raise ValueError('자동 감지 파일이 심볼릭 링크입니다.')
            shutil.copy2(source / name, destination)
        scripts = agent / 'Scripts'
        if scripts.is_symlink():
            raise ValueError('자동 감지 스크립트 경로가 심볼릭 링크입니다.')
        scripts.mkdir(exist_ok=True, mode=0o700)
        for name in ('patch.sh', 'nib.py', 'watch.sh', 'automation.py', 'manage.py'):
            destination = scripts / name
            if destination.is_symlink():
                raise ValueError('자동 감지 파일이 심볼릭 링크입니다.')
            shutil.copy2(source / 'Scripts' / name, destination)
    for name in ('Apply.command', 'Restore.command'):
        obsolete = agent / name
        if obsolete.is_symlink() or obsolete.is_file():
            obsolete.unlink()
    payload = {
        'Label': LABEL,
        'ProgramArguments': ['/bin/bash', str(agent / 'Scripts/watch.sh')],
        'RunAtLoad': True,
        'StartInterval': 300,
        'ProcessType': 'Background',
        'LimitLoadToSessionType': 'Aqua',
    }
    temporary = plist.with_suffix('.tmp')
    with temporary.open('xb') as stream:
        plistlib.dump(payload, stream)
    temporary.chmod(0o600)
    temporary.replace(plist)
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(plist)], check=True)
    print('업데이트 감지를 켰습니다. 로그인할 때와 300초마다 확인합니다.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ('install', 'remove'):
            raise ValueError('install 또는 remove를 지정해 주세요.')
        configure(sys.argv[1])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
