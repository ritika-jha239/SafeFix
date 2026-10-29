"""Build an exact-revision scientific runner, outside the application checkout."""
import argparse
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from .issues import git, IssueError
from .environment import inspect_project, image_name, repository_name
from .cache import checkout,environment_key,locked,directory as cache_directory,write_json,read_json,CacheError

PROFILES={
 'pandas-dev/pandas':('pandas','safefix-pandas:local'),
 'scikit-learn/scikit-learn':('sklearn','safefix-sklearn:local'),
 'sympy/sympy':('sympy','safefix-sympy:local'),
}

EVALUATION_REVISIONS={
 'pandas-dev/pandas':'0988929a21cdcc933b380871a622138eb18cc207',
 'scikit-learn/scikit-learn':'d685424bec8f8585d8017c1aab1db7535d3fa03d',
 'sympy/sympy':'16fa855354eb7bcabd3fe10993841e03b1382692',
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository',nargs='?',help='Any public GitHub owner/repository')
    parser.add_argument('--python',choices=('3.10','3.11','3.12','3.13','3.14'),help='Override the detected Python version')
    parser.add_argument('--project-dir',default='.',help='Project subdirectory for a monorepo')
    parser.add_argument('--generic',action='store_true',help='Use metadata-driven builder even for benchmark repositories')
    parser.add_argument('--evaluation-set',action='store_true',help='Build all three pinned runners for the five documented issues')
    parser.add_argument('--native',action='store_true',help='Include compiler/system build dependencies even if no native sources were detected')
    parser.add_argument('--force',action='store_true',help='Rebuild even when an exact environment is cached')
    parser.add_argument('--ref',help='Optional full commit SHA to build')
    args=parser.parse_args()
    if args.evaluation_set:
        if args.repository or args.ref or args.python or args.generic or args.native or args.project_dir!='.': parser.error('--evaluation-set only accepts the optional --force flag')
        for repository,revision in EVALUATION_REVISIONS.items():
            subprocess.run([sys.executable,'-m','safefix.prepare_runner',repository,'--ref',revision,*(['--force'] if args.force else [])],check=True)
        return
    if not args.repository:parser.error('Choose a repository or --evaluation-set')
    if args.ref and (len(args.ref)!=40 or any(c not in '0123456789abcdef' for c in args.ref)):
        parser.error('--ref must be a full lowercase commit SHA')
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    docker=['docker','--host=unix:///var/run/docker.sock']
    subprocess.run([*docker,'info'],env=env,check=True,stdout=subprocess.DEVNULL)
    args.repository=repository_name(args.repository).lower()
    specialized=args.repository in PROFILES and not args.generic and args.project_dir=='.' and not args.python
    package,image=PROFILES[args.repository] if specialized else ('',image_name(args.repository))
    templates=Path(__file__).resolve().parent.parent/'runner'
    with tempfile.TemporaryDirectory(prefix='safefix-build-') as directory:
        source=Path(directory)/'source'
        snapshot=checkout(args.repository,source,args.ref)
        sha=snapshot['commit']
        print(('Repository cache hit' if snapshot['cache_hit'] else 'Fetched repository into shared cache')+f': {args.repository} at {sha}',flush=True)
        metadata=inspect_project(source,args.project_dir,args.python)
        if args.native:metadata['needs_native']=True
        def helper(filename, content):
            target=source/filename
            if target.is_symlink() or target.is_file():target.unlink()
            target.write_text(content)
        if specialized:
            helper('.safefix-runner-entrypoint.py',(templates/'scientific-entrypoint.py').read_text())
            recipe='scientific.Dockerfile'
            extra=['--build-arg','PACKAGE='+package]
        else:
            print('Detected environment: '+json.dumps(metadata),flush=True)
            helper('.safefix-environment.json',json.dumps(metadata))
            helper('.safefix-build.py',(templates/'build-project.py').read_text())
            helper('.safefix-entrypoint.py',(templates/'project-entrypoint.py').read_text())
            recipe='project.Dockerfile'
            extra=['--build-arg','PYTHON_VERSION='+metadata['python'],'--build-arg','NATIVE_BUILD='+('1' if metadata['needs_native'] else '0')]
        helper('.dockerignore','__pycache__\n.pytest_cache\n.venv\n')
        key=environment_key(args.repository,sha,metadata,templates,recipe,source)
        cache_tag='safefix-env-'+key+':local'
        record_path=cache_directory()/'environments'/(key+'.json')
        def inspect_cached(reference):
            if not isinstance(reference,str):return None
            check=subprocess.run([*docker,'image','inspect',reference,'--format','{{.Id}} {{json .Config.Labels}}'],env=env,capture_output=True,text=True)
            if check.returncode:return None
            try:
                identifier,_,raw=check.stdout.strip().partition(' ')
                labels=json.loads(raw) or {}
                if labels.get('safefix.cache_key')==key and labels.get('safefix.commit')==sha and labels.get('safefix.repository')==args.repository:
                    return identifier
            except ValueError:pass
            return None
        with locked('environment:'+key):
            record=read_json(record_path) or {}
            identifier=None if args.force else inspect_cached(record.get('image') if isinstance(record,dict) else None) or inspect_cached(cache_tag)
            hit=bool(identifier)
            if not identifier:
                print(f'Building {image} for {args.repository} at {sha}; native builds use two jobs.',flush=True)
                command=[*docker,'build','-f',str(templates/recipe),'-t',image,'-t',cache_tag,
                         '--build-arg','PROJECT='+args.repository,'--build-arg','COMMIT='+sha,
                         '--build-arg','ENV_FINGERPRINT='+key,*extra]
                if args.force:command.append('--no-cache')
                ca=Path('/etc/ssl/certs/ca-certificates.crt')
                if ca.exists():command.extend(['--secret','id=proxy_ca,src='+str(ca)])
                subprocess.run([*command,str(source)],env=env,check=True)
                identifier=inspect_cached(cache_tag)
                if not identifier:raise IssueError('Built image failed cache identity checks')
            else:
                subprocess.run([*docker,'tag',identifier,image],env=env,check=True)
                print(f'Environment cache hit: {image}; no dependency installation or native compilation required.',flush=True)
            result={'image':identifier,'tag':cache_tag,'repository':args.repository,'commit':sha,'cache_key':key,'cache_hit':hit}
            write_json(record_path,result)
            print('SAFEFIX_RUNNER_RESULT '+json.dumps(result),flush=True)
    print(f'Ready: {image}. The application will select this image and pin its checkout to {sha}.')

if __name__=='__main__':
    try:main()
    except (IssueError,subprocess.SubprocessError,OSError,ValueError,CacheError) as e:
        raise SystemExit(str(e) if isinstance(e,(ValueError,IssueError,CacheError)) else 'Runner preparation failed; inspect the build output and Docker/Git access.') from None
