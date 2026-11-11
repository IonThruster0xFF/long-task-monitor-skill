"""Install this skill for Codex or any harness with a supplied skills directory."""
import argparse
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit

NAME = 'long-task-monitor'
SOURCE = Path(__file__).resolve().parent / 'skills' / NAME
FILES = ['SKILL.md', 'agents/openai.yaml', 'scripts/report.py']


def server_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Server must be an http(s) URL without embedded credentials, query or fragment.')
    if parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Remote servers must use HTTPS.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('Invalid server port.') from None
    if '\n' in value or '\r' in value:
        raise ValueError('Invalid server URL.')
    return value.rstrip('/')


def install(args):
    server = server_url(args.server) if args.server else None
    token = os.environ.get('MONITOR_TOKEN') if server else None
    if token and (len(token) < 32 or '\n' in token or '\r' in token):
        raise ValueError('MONITOR_TOKEN must contain at least 32 characters and no newlines.')
    skills_dir = (Path(os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')) / 'skills'
                  if args.codex else args.dest.expanduser()).resolve()
    target = skills_dir / NAME
    if target.exists():
        if not target.is_dir() or not all((target / file).is_file() and (target / file).read_bytes() == (SOURCE / file).read_bytes() for file in FILES):
            raise ValueError('A different skill already exists at the destination; back it up and review before replacing it.')
        status = 'already_installed'
    else:
        skills_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        status = 'installed'
    config = args.config.expanduser().resolve()
    configuration = 'not_requested'
    if server:
        if config.exists():
            configuration = 'kept_existing'
        elif not token:
            configuration = 'needs_token'
        else:
            config.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                output.write(f'MONITOR_URL={server}\nMONITOR_TOKEN={token}\n')
            configuration = 'created'
    return {'ok': True, 'skill_path': str(target), 'installation': status,
            'config_path': str(config), 'configuration': configuration,
            'reporting_started': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--codex', action='store_true', help='Use CODEX_HOME/skills or ~/.codex/skills.')
    destination.add_argument('--dest', type=Path, help="The current harness's actual skills directory.")
    parser.add_argument('--server', help='Optional monitor URL; secret comes only from MONITOR_TOKEN environment variable.')
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('MONITOR_CONFIG') or str(Path.home() / '.config' / NAME / 'client.env')))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(install(args), ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        message = str(error) if isinstance(error, ValueError) else 'Installation or configuration could not be written; check paths and permissions.'
        print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
