"""Publish only server-retained, verified demo edits to a new branch."""
from collections import OrderedDict
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import uuid
from .agent import ROOT, DEMOS
from .sandbox import Tools

LOCK = threading.Lock()
JOBS = OrderedDict()

def retain(demo, original, content):
    if demo not in DEMOS:
        raise ValueError('Unknown demo')
    job_id = uuid.uuid4().hex
    with LOCK:
        JOBS[job_id] = dict(demo=demo, original=original, content=content, published=None, busy=False)
        while len(JOBS) > 50:
            JOBS.popitem(last=False)
    return job_id

def git(directory, *args):
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    try:
        return subprocess.run(['git', '-C', str(directory), *args], env=env,
                              check=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        # Git errors can include credential-bearing remote URLs; never return raw output.
        raise ValueError('Git operation failed. Check repository access and Git authentication in the server terminal.') from None

def destination():
    remote = git(ROOT, 'remote', 'get-url', 'origin')
    match = re.fullmatch(r'https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?', remote)
    if not match:
        match = re.fullmatch(r'git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?', remote)
    if not match:
        raise ValueError('Publishing requires an origin on github.com without credentials in its URL.')
    return remote, f'https://github.com/{match[1]}/{match[2]}'

def publish(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError('Verified run expired. Run the repair again before publishing.')
        if job['published']:
            return job['published']
        if job['busy']:
            raise ValueError('This repair is already being published.')
        job['busy'] = True
    try:
        remote, web = destination()
        branch = 'safefix/' + job['demo'] + '-' + job_id[:12]
        with tempfile.TemporaryDirectory(prefix='safefix-publish-') as directory:
            git(ROOT, 'clone', '--no-hardlinks', '--quiet', str(ROOT), directory)
            git(directory, 'remote', 'set-url', 'origin', remote)
            git(directory, 'fetch', '--quiet', 'origin', 'main')
            git(directory, 'checkout', '--quiet', '-b', branch, 'FETCH_HEAD')
            root = Path(directory)
            target = root / 'repos' / job['demo'] / 'solution.py'
            if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
                raise ValueError('Unsafe destination path')
            if target.read_text() != job['original']:
                raise ValueError('The destination source has changed. Refresh your checkout and run a new repair.')
            target.write_text(job['content'])
            result = Tools(target.parent).run_tests()
            if result['code'] != 0:
                raise ValueError('Destination tests did not pass; nothing was pushed.')
            path = target.relative_to(root).as_posix()
            git(directory, 'add', '--', path)
            git(directory, '-c', 'user.name=SafeFix Agent', '-c', 'user.email=safefix@users.noreply.github.com',
                'commit', '--quiet', '-m', 'Fix ' + job['demo'] + ' (verified by pytest)', '--', path)
            git(directory, 'push', 'origin', 'HEAD:refs/heads/' + branch)
            result = {'branch': branch, 'url': web + '/tree/' + branch,
                      'compare_url': web + '/compare/main...' + branch,
                      'commit': git(directory, 'rev-parse', 'HEAD')}
        with LOCK:
            job['published'] = result
        return result
    finally:
        with LOCK:
            job['busy'] = False
