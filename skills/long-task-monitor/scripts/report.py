#!/usr/bin/env python3
"""Harness-neutral task reporting; uses only the Python standard library."""
import argparse
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

CONFIG = Path.home() / '.config' / 'long-task-monitor' / 'client.env'
STATUS = {'start': 'running', 'pause': 'paused', 'resume': 'running', 'block': 'blocked',
          'complete': 'completed', 'fail': 'failed', 'cancel': 'cancelled'}


class ServerRejection(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'Server rejected event (HTTP {status}); check credentials and event fields.')


def read_config(path):
    result = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                key, separator, value = line.partition('=')
                if not separator:
                    raise ValueError('Invalid configuration line; use KEY=value.')
                result[key.strip()] = value.strip()
    return result


def read_json(path):
    value = json.load(sys.stdin) if path == '-' else json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Input must be a JSON object.')
    return value


def build_event(args):
    event = read_json(args.json) if args.json else {}
    if args.goal_file:
        snapshot = read_json(args.goal_file)
        goal = snapshot.get('goal', snapshot)
        if not isinstance(goal, dict) or not isinstance(goal.get('threadId'), str) or not goal['threadId'] or not isinstance(goal.get('objective'), str) or not goal['objective'].strip():
            raise ValueError('Goal snapshot must contain threadId and objective.')
        event.update(task_id='codex:' + goal['threadId'], harness='codex',
                     title=goal['objective'].splitlines()[0][:200])
        mapping = {'active': 'running', 'complete': 'completed', 'paused': 'paused', 'blocked': 'blocked',
                   'budget-limited': 'paused', 'usage-limited': 'paused'}
        if goal.get('status') in mapping:
            event['status'] = mapping[goal['status']]
    for key in ['task_id', 'title', 'overview', 'harness', 'current_step', 'progress', 'eta_seconds', 'message']:
        value = getattr(args, key)
        if value is not None:
            event[key] = value
    event.setdefault('task_id', os.environ.get('MONITOR_TASK_ID'))
    if not event.get('task_id'):
        raise ValueError('Set --task-id, MONITOR_TASK_ID, or provide --goal-file / --json.')
    if args.command in STATUS:
        event['status'] = STATUS[args.command]
    if args.command == 'heartbeat':
        event = {'task_id': event['task_id'], 'kind': 'heartbeat'}
    if args.unknown_progress:
        event['progress'] = None
    if args.clear_eta:
        event['eta_seconds'] = None
    event.setdefault('schema_version', 1)
    event.setdefault('event_id', args.event_id or str(uuid.uuid4()))
    event.setdefault('occurred_at', dt.datetime.now(dt.timezone.utc).isoformat())
    return event


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect must not forward a reporting secret to an unexpected host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_event(url, token, event, *, retries=2, timeout=5, sleep=time.sleep):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('MONITOR_URL must be an http(s) server URL without credentials, query or fragment.')
    if parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use HTTPS for a remote server to protect your reporting secret.')
    if not token or len(token) < 32:
        raise ValueError('Set MONITOR_TOKEN to the reporting secret (at least 32 characters).')
    encoded = json.dumps(event, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > 65_536:
        raise ValueError('Event is too large (maximum 64 KiB).')
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url.rstrip('/') + '/api/events', data=encoded,
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    for attempt in range(retries + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.loads(response.read(1_000_000))
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429) and error.code < 500:
                raise ServerRejection(error.code) from None
            last_error = f'HTTP {error.code}'
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as error:
            last_error = type(error).__name__
        if attempt < retries:
            sleep(2 ** attempt)
    raise RuntimeError(f'Reporting failed after {retries + 1} attempts ({last_error}).')


def save_pending(event):
    directory = CONFIG.parent / 'pending'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(uuid.uuid4()) + '.json')
    with path.open('x', encoding='utf-8') as stream:
        if os.name != 'nt':
            os.chmod(path, 0o600)
        json.dump(event, stream, ensure_ascii=False)
    return path


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('command', choices=[*STATUS, 'update', 'heartbeat', 'replay'])
    result.add_argument('--task-id')
    result.add_argument('--title')
    result.add_argument('--overview')
    result.add_argument('--harness')
    result.add_argument('--current-step')
    result.add_argument('--progress', type=float)
    result.add_argument('--eta-seconds', type=float)
    result.add_argument('--unknown-progress', action='store_true')
    result.add_argument('--clear-eta', action='store_true')
    result.add_argument('--message')
    result.add_argument('--event-id')
    source = result.add_mutually_exclusive_group()
    source.add_argument('--json', help='Protocol JSON file; - reads standard input.')
    source.add_argument('--goal-file', help='Saved Codex get_goal response; - reads standard input.')
    result.add_argument('--config', type=Path, default=Path(os.environ.get('MONITOR_CONFIG', CONFIG)))
    result.add_argument('--server', help='Overrides MONITOR_URL; never pass secrets as arguments.')
    result.add_argument('--retries', type=int, default=2, choices=range(0, 6))
    result.add_argument('--timeout', type=float, default=5)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    event = None
    try:
        if not 0 < args.timeout <= 30:
            raise ValueError('--timeout must be greater than 0 and at most 30 seconds.')
        config = read_config(args.config)
        url = args.server or os.environ.get('MONITOR_URL') or config.get('MONITOR_URL')
        token = os.environ.get('MONITOR_TOKEN') or config.get('MONITOR_TOKEN')
        if not url:
            raise ValueError('Configure MONITOR_URL first; see SKILL.md.')
        if args.command == 'replay':
            if not args.json or args.json == '-':
                raise ValueError('replay requires --json pointing to a saved pending event.')
            event = read_json(args.json)
        else:
            event = build_event(args)
        result = send_event(url, token, event, retries=args.retries, timeout=args.timeout)
        task = result['task']
        print(json.dumps({'ok': True, 'task_id': task['id'], 'status': task['status'],
                          'duplicate': result['duplicate'], 'ignored': result['ignored']}, ensure_ascii=False))
        # Replay files are left in place; caller can remove them after observing success.
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        message = str(error)
        # Do not include network exception details: they can contain URLs or secrets.
        output = {'ok': False, 'error': message if not isinstance(error, OSError) else 'Local file or network operation failed.'}
        if isinstance(error, ServerRejection):
            output['http_status'] = error.status
        if event is not None and args.command != 'replay' and not (isinstance(error, ServerRejection) and error.status == 410):
            try:
                output['pending_file'] = str(save_pending(event))
            except OSError:
                output['pending_error'] = 'Could not save pending event.'
        print(json.dumps(output, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
