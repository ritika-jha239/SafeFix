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
    parser.add_argument('--ref',help='Optional full commit SHA to build')
    args=parser.parse_args()
    if args.evaluation_set:
        if args.repository or args.ref: parser.error('--evaluation-set cannot be combined with repository or --ref')
        for repository,revision in EVALUATION_REVISIONS.items():
            subprocess.run([sys.executable,'-m','safefix.prepare_runner',repository,'--ref',revision],check=True)
        return
    if not args.repository:parser.error('Choose a repository or --evaluation-set')
    if args.ref and (len(args.ref)!=40 or any(c not in '0123456789abcdef' for c in args.ref)):
        parser.error('--ref must be a full lowercase commit SHA')
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    docker=['docker','--host=unix:///var/run/docker.sock']
    subprocess.run([*docker,'info'],env=env,check=True,stdout=subprocess.DEVNULL)
    repository_name(args.repository)
    specialized=args.repository in PROFILES and not args.generic and args.project_dir=='.' and not args.python
    package,image=PROFILES[args.repository] if specialized else ('',image_name(args.repository))
    templates=Path(__file__).resolve().parent.parent/'runner'
    with tempfile.TemporaryDirectory(prefix='safefix-build-') as directory:
        source=Path(directory)/'source'
        git(directory,'clone','--depth=1','--quiet',f'https://github.com/{args.repository}.git',str(source))
        if args.ref:
            git(source,'fetch','--depth=1','origin',args.ref)
            git(source,'checkout','--detach','FETCH_HEAD')
        sha=git(source,'rev-parse','HEAD')
        print(f'Building {image} for {args.repository} at {sha}; native builds use two jobs.',flush=True)
        def helper(filename, content):
            target=source/filename
            if target.is_symlink() or target.is_file():target.unlink()
            target.write_text(content)
        if specialized:
            helper('.safefix-runner-entrypoint.py',(templates/'scientific-entrypoint.py').read_text())
            recipe='scientific.Dockerfile'
            extra=['--build-arg','PACKAGE='+package]
        else:
            metadata=inspect_project(source,args.project_dir,args.python)
            print('Detected environment: '+json.dumps(metadata),flush=True)
            helper('.safefix-environment.json',json.dumps(metadata))
            helper('.safefix-build.py',(templates/'build-project.py').read_text())
            helper('.safefix-entrypoint.py',(templates/'project-entrypoint.py').read_text())
            recipe='project.Dockerfile'
            extra=['--build-arg','PYTHON_VERSION='+metadata['python']]
        helper('.dockerignore','__pycache__\n.pytest_cache\n.venv\n')
        command=[*docker,'build','-f',str(templates/recipe),'-t',image,
                 '--build-arg','PROJECT='+args.repository,'--build-arg','COMMIT='+sha,*extra]
        ca=Path('/etc/ssl/certs/ca-certificates.crt')
        if ca.exists():command.extend(['--secret','id=proxy_ca,src='+str(ca)])
        subprocess.run([*command,str(source)],env=env,check=True)
    print(f'Ready: {image}. The application will select this image and pin its checkout to {sha}.')

if __name__=='__main__':
    try:main()
    except (IssueError,subprocess.SubprocessError,OSError,ValueError) as e:
        raise SystemExit(str(e) if isinstance(e,(ValueError,IssueError)) else 'Runner preparation failed; inspect the build output and Docker/Git access.') from None
