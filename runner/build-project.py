"""Executed only inside an isolated dependency-build container, never on host."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path('/opt/source')
config=json.loads(Path('/opt/safefix-environment.json').read_text())
project=(root/config['project_dir']).resolve()
if not project.is_relative_to(root):raise SystemExit('Invalid project path')
for file in config['requirements']:
    path=(root/file).resolve()
    if not path.is_relative_to(root):raise SystemExit('Invalid requirements path')
    subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir','-r',str(path)],check=True)
if config.get('test_dependencies'):
    subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir',*config['test_dependencies']],check=True)
if config['packaged']:
    target=str(project)+(f'[{config["test_extra"]}]' if config['test_extra'] else '')
    command=[sys.executable,'-m','pip','install','--no-cache-dir']
    if config['backend']=='mesonpy':command+=['--config-settings=compile-args=-j2']
    subprocess.run([*command,target],check=True)
