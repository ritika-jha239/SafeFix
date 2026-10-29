"""Loopback-only UI for trusted bundled demo repositories."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from .agent import DEMOS, repair

from pathlib import Path
import re

PAGE = (Path(__file__).parent / 'static' / 'index.html').read_text()

def validate_issue(value):
    if not isinstance(value, str):
        raise ValueError('Invalid issue link')
    if value and not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*/?', value):
        raise ValueError('Use a GitHub issue URL')
    return value

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/health'):
            self.send_error(404); return
        body = (PAGE if self.path == '/' else 'ok').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if self.path == '/' else 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        # Prevent cross-origin websites from triggering local jobs.
        if self.path != '/repair' or self.headers.get('Origin') not in (None, 'http://127.0.0.1:8501', 'http://localhost:8501'):
            self.send_error(403); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024: raise ValueError('Invalid body size')
            data = json.loads(self.rfile.read(length))
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
    ThreadingHTTPServer(('127.0.0.1',8501), Handler).serve_forever()
