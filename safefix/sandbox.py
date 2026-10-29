"""Path and command guardrails. This is NOT an OS security sandbox."""
from pathlib import Path
import os
import subprocess
import sys

class Tools:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.blocked = []

    def deny(self, reason):
        self.blocked.append(reason)
        raise ValueError(reason)

    def path(self, name, write=False):
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root) or p.suffix != '.py':
            self.deny(f'Blocked path: {name}')
        if write and p.name != 'solution.py':
            self.deny(f'Only solution.py may be edited: {name}')
        return p

    def read_file(self, path):
        return self.path(path).read_text()[:30000]

    def write_file(self, path, content):
        if len(content) > 30000:
            self.deny('File size limit exceeded')
        self.path(path, write=True).write_text(content)

    def command(self, argv):
        if argv != ['pytest']:
            self.deny(f'Blocked command: {argv}')
        return self.run_tests()

    def run_tests(self):
        # A clean child environment prevents accidental inheritance of API keys.
        env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
        env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        try:
            with __import__('tempfile').TemporaryFile() as out:
                p = subprocess.Popen([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-c', '/dev/null', 'test_solution.py'],
                                     cwd=self.root, env=env, stdout=out, stderr=subprocess.STDOUT,
                                     start_new_session=True)
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                    return {'code': 124, 'output': 'Test timeout (15 seconds)'}
                out.seek(0)
                return {'code': p.returncode, 'output': out.read(30000).decode(errors='replace')}
        except OSError as e:
            return {'code': 125, 'output': str(e)}
