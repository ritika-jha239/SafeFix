"""Loopback-only UI for trusted bundled demo repositories."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from .agent import DEMOS, repair

from pathlib import Path
import re
from .publish import publish, destination

PAGE = (Path(__file__).parent / 'static' / 'index.html').read_text()

def validate_issue(value):
    if not isinstance(value, str):
        raise ValueError('Invalid issue link')
    if value and not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*/?', value):
        raise ValueError('Use a GitHub issue URL')
    return value

class Handler(BaseHTTPRequestHandler):
    def publish_job(self, job_id):
        try:
            payload = {'success': True, **publish(job_id)}
            code = 200
        except (ValueError, OSError) as e:
            payload = {'success': False, 'message': str(e) if isinstance(e, ValueError) else 'Unable to prepare publishing workspace.'}
            code = 400
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/destination':
            try:
                body = json.dumps({'repository': destination()[1]}).encode()
            except ValueError:
                body = json.dumps({'repository': None}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
            return
        if self.path not in ('/', '/health'):
            self.send_error(404); return
        body = (PAGE if self.path == '/' else 'ok').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if self.path == '/' else 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        # Prevent cross-origin websites from triggering local jobs.
        if self.path not in ('/repair', '/publish') or self.headers.get('Origin') not in (None, 'http://127.0.0.1:8501', 'http://localhost:8501'):
            self.send_error(403); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024: raise ValueError('Invalid body size')
            data = json.loads(self.rfile.read(length))
            if self.path == '/publish':
                if not isinstance(data, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(data.get('job_id', ''))):
                    raise ValueError('Invalid verified run ID')
                return self.publish_job(data['job_id'])
            if data.get('demo') not in DEMOS or data.get('mode') not in ('offline','live'):
                raise ValueError('Invalid demo or mode')
            issue = validate_issue(data.get('issue', ''))
        except (ValueError, TypeError, AttributeError):
            self.send_error(400); return
        self.send_response(200); self.send_header('Content-Type','application/x-ndjson'); self.end_headers()
        try:
            self.wfile.write((json.dumps({'kind':'accepted', 'issue':issue, 'demo':data['demo'], 'mode':data['mode'], 'message':'Issue link attached as context only; executing selected bundled demo. GitHub content is not fetched.'})+'\n').encode()); self.wfile.flush()
            for event in repair(data['demo'], data['mode']):
                self.wfile.write((json.dumps(event)+'\n').encode()); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.wfile.write((json.dumps({'kind':'error','message':'Repair failed. Check API configuration and provider access; credentials are never logged.'})+'\n').encode())

if __name__ == '__main__':
    print('SafeFix running at http://127.0.0.1:8501 — leave this terminal open. Ctrl+C to stop.', flush=True)
    try:
        ThreadingHTTPServer(('127.0.0.1',8501), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nSafeFix stopped.')
