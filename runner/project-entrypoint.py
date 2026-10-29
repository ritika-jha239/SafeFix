"""Execute checkout source plus matching native artifacts in a temporary tree."""
import json
import os
from pathlib import Path
import shutil
import sys
import sysconfig

source=Path('/repo');work=Path('/tmp/work')
config=json.loads(Path('/opt/safefix-environment.json').read_text())
ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','.venv','build','dist','doc','docs','.github','asv_benchmarks')
shutil.copytree(source,work,ignore=ignore)
site=Path(sysconfig.get_paths()['purelib'])
for relative in config['packages']:
    checkout=work/relative
    if not checkout.resolve().is_relative_to(work):raise SystemExit('Invalid package path')
    installed=site/Path(relative).name
    if installed.is_dir():
        for artifact in installed.rglob('*'):
            if artifact.is_file() and '__pycache__' not in artifact.parts:
                target=checkout/artifact.relative_to(installed)
                if not target.exists():
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(artifact,target)
project=(work/config['project_dir']).resolve()
os.chdir(work)
os.environ['PYTHONPATH']=':'.join(str(p) for p in (project/'src',project/'python',project,work/'src',work))
args=sys.argv[1:]
if args and args[0]=='python':args=args[1:]
os.execv(sys.executable,[sys.executable,*args])
