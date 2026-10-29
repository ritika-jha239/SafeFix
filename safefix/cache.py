"""Private disk caches with cross-process locks; job source stays isolated."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import time
import uuid
from .environment import repository_name

class CacheError(RuntimeError):
    pass


def directory():
    root=Path(os.getenv('SAFEFIX_CACHE_DIR',str(Path.home()/'.cache'/'safefix'))).expanduser()
    try:root.mkdir(parents=True,exist_ok=True,mode=0o700)
    except OSError:raise CacheError('Cache directory is not writable. Set SAFEFIX_CACHE_DIR to a writable private directory.') from None
    return root


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@contextmanager
def locked(name):
    folder=directory()/'locks';folder.mkdir(exist_ok=True,mode=0o700)
    with (folder/(digest(name)+'.lock')).open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def read_json(path):
    try:
        if path.stat().st_size>64000000:return None
        return json.loads(path.read_text())
    except (OSError,ValueError):return None


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,separators=(',',':')))
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def run_git(root,*args,check=True):
    try:
        result=subprocess.run(['git','-C',str(root),*args],check=check,capture_output=True,text=True,timeout=120,
            env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
        return result.stdout.strip() if result.returncode==0 else None
    except (OSError,subprocess.SubprocessError):
        raise CacheError('Repository cache could not fetch/check out source. Check GitHub access and Git availability.') from None


def checkout(repository,target,ref=None):
    repository_name(repository)
    if ref is not None and not re.fullmatch('[a-f0-9]{40}',ref):raise CacheError('Cached checkout ref must be a full commit SHA')
    key=digest(repository.lower());base=directory()/'repositories';base.mkdir(exist_ok=True,mode=0o700)
    bare=base/(key+'.git');state_path=base/(key+'.json')
    with locked('repository:'+repository.lower()):
        if not bare.exists():
            run_git(base,'init','--bare',str(bare))
            run_git(bare,'remote','add','origin',f'https://github.com/{repository}.git')
            run_git(bare,'symbolic-ref','HEAD','refs/heads/safefix-cache')
        state=read_json(state_path)
        if not isinstance(state,dict):state={}
        if not isinstance(state.get('fetched_at',0),(float,int)):state={}
        try:ttl=max(0,min(86400,int(os.getenv('SAFEFIX_GIT_REFRESH_SECONDS','60'))))
        except ValueError:ttl=60
        selected=ref or state.get('head')
        if selected is not None and (not isinstance(selected,str) or not re.fullmatch('[a-f0-9]{40}',selected)):selected=None
        exists=bool(selected and run_git(bare,'cat-file','-e',selected+'^{commit}',check=False) is not None)
        hit=exists and (ref is not None or time.time()-state.get('fetched_at',0)<ttl)
        if not hit:
            run_git(bare,'-c','gc.auto=0','fetch','--depth=1','--quiet','origin',ref or 'HEAD')
            selected=run_git(bare,'rev-parse','FETCH_HEAD^{commit}')
            if ref is None:
                state={'head':selected,'fetched_at':time.time()}
                write_json(state_path,state)
        # Keep fetched commits reachable; no cache GC/pruning while jobs use them.
        run_git(bare,'update-ref','refs/safefix/commits/'+selected,selected)
        run_git(bare,'update-ref','refs/heads/safefix-cache',selected)
        run_git(base,'clone','--local','--no-checkout','--quiet',str(bare),str(target))
        run_git(target,'remote','set-url','origin',f'https://github.com/{repository}.git')
        run_git(target,'checkout','--quiet','--detach',selected)
    return {'commit':selected,'cache_hit':hit}


def environment_key(repository,commit,metadata,templates,recipe,root=None):
    # Full source revision is deliberately retained: native/build-hook inputs can
    # depend on any tracked file, so dependency equality alone is not ABI proof.
    helpers=['scientific-entrypoint.py'] if recipe=='scientific.Dockerfile' else ['project-entrypoint.py','build-project.py']
    inputs={}
    if root is not None:
        root=Path(root)
        names=set(metadata.get('manifests',[])+metadata.get('requirements',[]))
        names.update(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '.git' not in p.parts and (p.name in ('uv.lock','poetry.lock','pdm.lock','Pipfile.lock') or p.name.startswith('requirements') and p.suffix=='.txt'))
        for name in sorted(names):
            path=(root/name).resolve()
            if path.is_relative_to(root.resolve()) and path.is_file():inputs[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    payload={'version':1,'platform':[platform.system(),platform.machine(),os.getenv('DOCKER_DEFAULT_PLATFORM','native')],'inputs':inputs,'repository':repository.lower(),'commit':commit,'metadata':metadata,
             'recipe':{name:hashlib.sha256((templates/name).read_bytes()).hexdigest() for name in [recipe,*helpers]}}
    return digest(payload)


def source_index(tools):
    repository=getattr(tools,'repository',None);commit=getattr(tools,'revision',None)
    path=None
    if repository and commit and re.fullmatch('[a-f0-9]{40}',commit):
        path=directory()/'indexes'/(digest([repository.lower(),commit,2])+'.json')
        cached=read_json(path)
        if isinstance(cached,dict) and isinstance(cached.get('entries'),list):return cached['entries'],True
    entries=[]
    for name in tools.files[:10000]:
        try:source=tools.read_file(name)
        except (OSError,ValueError,UnicodeError):continue
        definitions=sorted(set(re.findall(r'\b(?:def|class)\s+([A-Za-z_]\w*)',source)))
        words=sorted(set(re.findall(r'\b[A-Za-z_]\w{3,}\b',source)))[:1200]
        entries.append({'path':name,'definitions':definitions,'words':words})
    if path:write_json(path,{'entries':entries})
    return entries,False
