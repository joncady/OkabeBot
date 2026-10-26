#!/usr/bin/env python3
"""Create a private, self-contained Mac login installation outside Documents.

Run with the prepared controller environment. Stop the foreground controller first.
Existing installations are refused: deploy updates deliberately, preserving state.
"""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def copy_environment(source, destination):
    shutil.copytree(source, destination, symlinks=True)
    for site in destination.glob('lib/python*/site-packages'):
        for editable in site.glob('__editable__*'):
            if editable.is_dir():
                shutil.rmtree(editable)
            else:
                editable.unlink()
        (site / 'okabebot-runtime.pth').write_text(str(destination.parent) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'okabebot.local.json')
    parser.add_argument('--destination', type=Path,
                        default=Path.home() / 'Library/Application Support/OkabeBot')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('This installer is for macOS')
    source = args.config.resolve().parent
    destination = args.destination.expanduser().resolve()
    if destination.exists():
        raise SystemExit('Destination already exists; preserve its private state before updating')
    config = json.loads(args.config.read_text())
    state = (source / config.get('state_dir', '.local')).resolve()
    for lockpath in (state / 'runtime/supervisor.lock', state / 'ptt/bridge.lock'):
        if lockpath.exists():
            with lockpath.open('r') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise SystemExit('Stop the existing controller/supervisor before installing')
    if not (Path(sys.prefix) / 'pyvenv.cfg').is_file():
        raise SystemExit('Run this installer with the prepared controller virtual environment')
    command = config.get('speech', {}).get('worker_command', [])
    if command and not ((source / command[0]).absolute().parent.parent / 'pyvenv.cfg').is_file():
        raise SystemExit('The bundled speech worker needs its own prepared virtual environment')
    destination.mkdir(parents=True, mode=0o700)
    for name in ('okabebot', 'scripts', 'infra'):
        shutil.copytree(ROOT / name, destination / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    copy_environment(Path(sys.prefix), destination / '.venv')
    target_state = destination / '.local'
    target_state.mkdir(mode=0o700)
    # Persistent application data only; never copy the entire development scratch folder.
    names = ('notification-sources.json', 'notification-policy.json', 'profile.json',
             'character.json', 'speech-settings.json', 'button-settings.json',
             'spotify-tokens.json', 'content-context.json', 'notification-token',
             'controller-token', 'github-relay.json')
    for name in names:
        if (state / name).is_file():
            shutil.copy2(state / name, target_state / name)
            (target_state / name).chmod(0o600)
    for name in ('notifications.sqlite3', 'sports-resolver.sqlite3', 'movie-metadata.sqlite3'):
        if (state / name).is_file():
            with sqlite3.connect(state / name) as db, sqlite3.connect(target_state / name) as out:
                db.backup(out)
            (target_state / name).chmod(0o600)
    for name in ('models', 'ptt'):
        if (state / name).is_dir():
            shutil.copytree(state / name, target_state / name,
                            ignore=shutil.ignore_patterns('*.lock', 'control.json', '*.log'))
    for endpoint in config.get('devices', {}).values():
        if endpoint.get('ssh_key'):
            key = (source / endpoint['ssh_key']).resolve()
            target_key = target_state / key.name
            shutil.copy2(key, target_key)
            target_key.chmod(0o600)
            endpoint['ssh_key'] = str(target_key)
    settings = config.get('speech', {})
    command = settings.get('worker_command', [])
    if command:
        executable = (source / command[0]).absolute()
        environment = executable.parent.parent
        copy_environment(environment, destination / '.voice-venv')
        command[0] = str(destination / '.voice-venv/bin/python')
        for index in range(1, len(command)):
            candidate = source / command[index]
            if candidate.is_file():
                if command[index - 1] == '--manifest':
                    manifest = json.loads(candidate.read_text())
                    references = target_state / 'voice-references'
                    references.mkdir(mode=0o700)
                    for entry in manifest.values():
                        audio = (candidate.parent / entry['audio']).resolve()
                        shutil.copy2(audio, references / audio.name)
                        entry['audio'] = str(references / audio.name)
                    target = references / 'references.json'
                    target.write_text(json.dumps(manifest, indent=2))
                    target.chmod(0o600)
                    command[index] = str(target)
                elif candidate.resolve().is_relative_to(ROOT):
                    command[index] = str(destination / candidate.resolve().relative_to(ROOT))
        socket = str(target_state / 'qwen-tts.sock')
        settings['local_socket'] = socket
        if '--socket' in command:
            command[command.index('--socket') + 1] = socket
    config['state_dir'] = str(target_state)
    config.setdefault('codex', {})['cwd'] = str(destination)
    if (source / '.env').is_file():
        shutil.copy2(source / '.env', destination / '.env')
        (destination / '.env').chmod(0o600)
    target_config = destination / 'okabebot.local.json'
    target_config.write_text(json.dumps(config, indent=2) + '\n')
    target_config.chmod(0o600)
    subprocess.run([str(destination / '.venv/bin/python'), '-m', 'okabebot.runtime',
                    '--config', str(target_config), '--install'], cwd=destination, check=True)
    print('Start manually with:', destination / 'scripts/start-mac.sh')


if __name__ == '__main__':
    main()
