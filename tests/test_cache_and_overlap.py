import json
from pathlib import Path
import subprocess
import threading
import pytest
from safefix import cache,issues
from safefix.execution import overlap


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()


@pytest.fixture
def local_repository(tmp_path,monkeypatch):
    monkeypatch.setenv('SAFEFIX_CACHE_DIR',str(tmp_path/'cache'))
    origin=tmp_path/'origin';origin.mkdir()
    git(origin,'init','-b','main')
    (origin/'library.py').write_text('def value():\n    return 1\n')
    git(origin,'add','.')
    git(origin,'-c','user.name=Test','-c','user.email=test@example.org','commit','-m','initial')
    folder=cache.directory()/'repositories';folder.mkdir()
    bare=folder/(cache.digest('owner/library')+'.git')
    git(folder,'init','--bare',str(bare));git(bare,'remote','add','origin',str(origin))
    git(bare,'symbolic-ref','HEAD','refs/heads/safefix-cache')
    return origin,tmp_path


def test_checkouts_fetch_once_and_isolate_mutations(local_repository,monkeypatch):
    origin,root=local_repository
    real=cache.run_git;fetches=[]
    def tracked(path,*args,**kwargs):
        if 'fetch' in args:fetches.append(args)
        return real(path,*args,**kwargs)
    monkeypatch.setattr(cache,'run_git',tracked)
    first=cache.checkout('owner/library',root/'job1')
    (root/'job1/library.py').write_text('modified by one job')
    second=cache.checkout('owner/library',root/'job2')
    assert not first['cache_hit'] and second['cache_hit']
    assert len(fetches)==1 and first['commit']==second['commit']
    assert 'return 1' in (root/'job2/library.py').read_text()
    assert git(root/'job2','rev-parse','HEAD')==second['commit']
    assert not (root/'job2/.git/objects/info/alternates').exists()


def test_refresh_and_explicit_revision_cache(local_repository,monkeypatch):
    origin,root=local_repository
    old=cache.checkout('owner/library',root/'first')['commit']
    (origin/'library.py').write_text('def value():\n    return 2\n')
    git(origin,'add','.');git(origin,'-c','user.name=Test','-c','user.email=test@example.org','commit','-m','update')
    monkeypatch.setenv('SAFEFIX_GIT_REFRESH_SECONDS','0')
    fresh=cache.checkout('owner/library',root/'fresh')
    assert fresh['commit']!=old and not fresh['cache_hit']
    pinned=cache.checkout('owner/library',root/'pinned',old)
    assert pinned['commit']==old and pinned['cache_hit']
    assert 'return 1' in (root/'pinned/library.py').read_text()


def test_environment_fingerprint_invalidates_inputs(tmp_path):
    templates=tmp_path/'templates';templates.mkdir()
    for name in ('project.Dockerfile','project-entrypoint.py','build-project.py'):(templates/name).write_text(name)
    (tmp_path/'requirements.txt').write_text('example==1')
    metadata={'python':'3.12','requirements':['requirements.txt']}
    def key():return cache.environment_key('owner/library','a'*40,metadata,templates,'project.Dockerfile',tmp_path)
    original=key();assert key()==original
    (tmp_path/'requirements.txt').write_text('example==2');dependency=key();assert dependency!=original
    (templates/'project.Dockerfile').write_text('updated recipe');recipe=key();assert recipe!=dependency
    metadata['python']='3.13';assert key()!=recipe
    assert cache.environment_key('owner/library','b'*40,metadata,templates,'project.Dockerfile',tmp_path)!=key()


def test_source_index_reused_by_revision(local_repository):
    origin,root=local_repository
    sha=cache.checkout('owner/library',root/'source')['commit']
    tools=issues.RepoTools(root/'source');tools.repository='owner/library';tools.revision=sha
    first,hit=cache.source_index(tools);assert not hit
    tools.read_file=lambda path:(_ for _ in ()).throw(AssertionError('Cached index reread source'))
    second,hit=cache.source_index(tools)
    assert hit and first==second


def drain(generator):
    events=[]
    while True:
        try:events.append(next(generator))
        except StopIteration as result:return events,result.value


def test_analysis_finishes_before_environment_without_running_tests_early():
    analysis_started=threading.Event();plan_finished=threading.Event()
    def environment(stop):
        assert analysis_started.wait(3),'Analysis was blocked behind environment preparation'
        yield {'kind':'environment_log','message':'build started'}
        assert plan_finished.wait(3),'Plan did not finish concurrently'
        yield {'kind':'environment_ready','message':'build finished'}
        return ('immutable-image','a'*40)
    def analysis(stop):
        analysis_started.set()
        yield {'kind':'plan','message':'Actual source plan'}
        plan_finished.set()
        return {'plan':'Actual source plan'}
    events,results=drain(overlap(environment,analysis))
    kinds=[e['kind'] for e in events]
    assert kinds.index('plan')<kinds.index('environment_ready')
    assert results[0][1]=='a'*40 and results[1]['plan']=='Actual source plan'


def test_failure_cancels_other_phase_and_preserves_error():
    started=threading.Event();cancelled=threading.Event()
    def environment(stop):
        started.set()
        while not stop.wait(.01):
            yield {'kind':'environment_log','message':'building'}
        cancelled.set()
        return None
    def analysis(stop):
        assert started.wait(3)
        raise ValueError('precise planner failure')
        yield
    with pytest.raises(ValueError,match='precise planner failure'):drain(overlap(environment,analysis))
    assert cancelled.is_set()


def test_immediate_phase_factory_error_does_not_hang():
    def broken(stop):raise ValueError('factory failed immediately')
    def ready(stop):
        yield {'kind':'ready'}
        return 'done'
    with pytest.raises(ValueError,match='factory failed immediately'):drain(overlap(broken,ready))


def test_evaluation_force_flag_is_propagated(monkeypatch):
    from safefix import prepare_runner
    commands=[]
    monkeypatch.setattr(prepare_runner.sys,'argv',['prepare_runner','--evaluation-set','--force'])
    monkeypatch.setattr(prepare_runner.subprocess,'run',lambda command,**kwargs:commands.append(command))
    prepare_runner.main()
    assert len(commands)==3 and all('--force' in command for command in commands)


def test_metadata_symlink_cannot_read_outside_checkout(tmp_path):
    from safefix.environment import inspect_project
    root=tmp_path/'checkout';root.mkdir()
    outside=tmp_path/'private.toml';outside.write_text('[project]\nname="private"')
    (root/'pyproject.toml').symlink_to(outside)
    with pytest.raises(ValueError,match='escapes'):inspect_project(root)


def test_explicit_runner_is_not_rebuilt_by_auto_mode(monkeypatch):
    monkeypatch.setenv('SAFEFIX_AUTO_PREPARE','1')
    monkeypatch.setenv('SAFEFIX_RUNNER_IMAGE','custom:local')
    monkeypatch.setattr(issues.subprocess,'Popen',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Explicit runner was rebuilt')))
    events,result=drain(issues.prepare_environment('owner/library',ref='a'*40,existing=('immutable-custom','a'*40)))
    assert result==('immutable-custom','a'*40)
    assert events[0]['cache_hit']
