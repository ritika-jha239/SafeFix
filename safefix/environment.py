"""Read project metadata without importing or executing repository code."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import tomllib
from packaging.specifiers import SpecifierSet, InvalidSpecifier

VERSIONS=('3.12','3.13','3.14','3.11','3.10')

def repository_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value) or any(x in ('.','..') for x in value.split('/')):
        raise ValueError('Use GitHub owner/repository, without a URL or credentials')
    return value

def image_name(repository):
    repository_name(repository)
    return 'safefix-repo-'+hashlib.sha256(repository.lower().encode()).hexdigest()[:16]+':local'

def inspect_project(root,project_dir='.',python=None):
    root=Path(root).resolve();project=(root/project_dir).resolve()
    if not project.is_relative_to(root) or not project.is_dir():raise ValueError('Project directory must be inside the checkout')
    data={};pyproject=project/'pyproject.toml'
    if pyproject.is_file():
        if pyproject.stat().st_size>1000000:raise ValueError('Project metadata exceeds limit')
        data=tomllib.loads(pyproject.read_text())
    declared=data.get('project',{})
    if not isinstance(declared,dict) or not isinstance(data.get('build-system',{}),dict) or not isinstance(data.get('tool',{}),dict):raise ValueError('Invalid project/build metadata tables')
    requires=declared.get('requires-python','')
    if not isinstance(requires,str):raise ValueError('requires-python must be text')
    cfg=configparser.ConfigParser(interpolation=None)
    if (project/'setup.cfg').is_file():
        cfg.read(project/'setup.cfg')
        requires=requires or cfg.get('options','python_requires',fallback='')
    try:spec=SpecifierSet(requires)
    except InvalidSpecifier:raise ValueError('Invalid requires-python metadata; choose a supported runtime explicitly') from None
    candidates=[python] if python else list(VERSIONS)
    compatible=[v for v in candidates if v in VERSIONS and (not requires or spec.contains(v+'.0'))]
    if not compatible:raise ValueError(f'No supported Python runtime satisfies {requires!r}; supported versions: '+', '.join(VERSIONS))
    packages=[]
    for base in (project,project/'src',project/'python'):
        if not base.is_dir():continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.') and child.name not in ('tests','test','docs','doc','examples','build_tools','maint_tools','benchmarks','runner','evaluations'):
                if (child/'__init__.py').is_file() or base!=project and any(child.rglob('*.py')):
                    packages.append(child.relative_to(root).as_posix())
    extras=declared.get('optional-dependencies',{})
    extra=next((x for x in ('test','tests','testing') if x in extras or cfg.has_option('options.extras_require',x)),None)
    requirements=[p.relative_to(root).as_posix() for p in [project/'requirements.txt',project/'requirements/test.txt',project/'requirements/tests.txt',project/'tests/requirements.txt',project/'requirements-test.txt',project/'test-requirements.txt'] if p.is_file()]
    groups=data.get('dependency-groups',{})
    test_dependencies=[]
    def group(name,seen=None):
        seen=set() if seen is None else seen
        if name in seen:raise ValueError('Cyclic dependency group')
        seen=seen|{name}
        result=[]
        for dependency in groups.get(name,[]):
            if isinstance(dependency,str):
                from packaging.requirements import Requirement
                Requirement(dependency)
                result.append(dependency)
            elif isinstance(dependency,dict) and isinstance(dependency.get('include-group'),str):result.extend(group(dependency['include-group'],seen))
            else:raise ValueError('Invalid test dependency group entry')
        return result
    if isinstance(groups,dict):
        target=next((g for g in ('test','tests','testing') if g in groups),None)
        if target:test_dependencies=group(target)
    backend=data.get('build-system',{}).get('build-backend','')
    return {'project_dir':project.relative_to(root).as_posix(),'python':compatible[0],
            'requires_python':requires,'name':declared.get('name') or cfg.get('metadata','name',fallback=project.name),
            'backend':backend,'packaged':bool(declared or data.get('build-system') or data.get('tool',{}).get('poetry') or any((project/p).is_file() for p in ('setup.py','setup.cfg'))),
            'packages':sorted(set(packages)),'test_extra':extra,'requirements':requirements,'test_dependencies':test_dependencies,
            'manifests':[p.relative_to(root).as_posix() for p in [pyproject,project/'setup.cfg',project/'setup.py',project/'pytest.ini',project/'tox.ini'] if p.is_file()]}
