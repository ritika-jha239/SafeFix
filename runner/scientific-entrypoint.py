"""Merge compiled artifacts from the exact image revision with edited source."""
import os
from pathlib import Path
import shutil
import sys
import sysconfig

source=Path('/repo')
work=Path('/tmp/work')
package=os.environ['SAFEFIX_OVERLAY_PACKAGE']
installed=Path(sysconfig.get_paths()['purelib'])/package
if not installed.is_dir():
    raise SystemExit('Prepared runner package is missing')
ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','build','dist','doc','docs','.github','asv_benchmarks')
shutil.copytree(source,work,ignore=ignore)
# Add only missing generated/native files. Existing source (including edits) wins.
for artifact in installed.rglob('*'):
    if artifact.is_file() and '__pycache__' not in artifact.parts:
        target=work/package/artifact.relative_to(installed)
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(artifact,target)
os.chdir(work)
os.environ['PYTHONPATH']=str(work/'src')+':'+str(work)
args=sys.argv[1:]
if args and args[0]=='python':args=args[1:]
os.execv(sys.executable,[sys.executable,*args])
