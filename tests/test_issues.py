import json
from pathlib import Path
import pytest
from safefix import issues


def test_issue_parser_uses_actual_report():
    data={'issue':{'body':'Actual bug: integer dictionary keys fail'}}
    page='<title>Integer keys crash · Issue #42 · owner/repo · GitHub</title><script type="application/json">'+json.dumps(data)+'</script>'
    title,body=issues.parse_issue(page,42)
    assert title=='Integer keys crash'
    assert 'integer dictionary' in body
    with pytest.raises(issues.IssueError): issues.parse_issue(page,43)

@pytest.mark.parametrize('url',['https://evil.example/o/r/issues/1','https://github.com/../r/issues/1','https://github.com/o/r/pull/1'])
def test_issue_identity_rejects_invalid(url):
    with pytest.raises(issues.IssueError): issues.identity(url)

@pytest.fixture
def repository(tmp_path, monkeypatch):
    (tmp_path/'maths.py').write_text('def total(n):\n    return sum(range(n))\n')
    (tmp_path/'test_maths.py').write_text('from maths import total\n\ndef test_sum():\n    assert total(5)==15\n')
    monkeypatch.setattr(issues,'git',lambda root,*args:'maths.py\ntest_maths.py' if args==('ls-files',) else 'abc123')
    return tmp_path

def test_real_source_paths_and_diff(repository):
    tools=issues.RepoTools(repository)
    for path in ['../escape.py','not_tracked.py','test_maths.py']:
        with pytest.raises(ValueError): tools.write_file(path,'bad')
    tools.write_file('maths.py','def total(n):\n    return sum(range(n + 1))\n')
    assert 'a/maths.py' in tools.diff()
    assert '+    return sum(range(n + 1))' in tools.diff()
    assert 'solution.py' not in tools.diff()
    with pytest.raises(issues.IssueError):tools.select_tests([])
    tools.select_tests(['test_maths.py'])


def test_missing_docker_does_not_run_on_host(repository,monkeypatch):
    tools=issues.RepoTools(repository);tools.select_tests(['test_maths.py'])
    monkeypatch.setattr(issues.shutil,'which',lambda name:None)
    with pytest.raises(issues.IssueError,match='Docker is required'):tools.run_tests()


def configure_flow(repository,monkeypatch, baseline):
    monkeypatch.setattr(issues,'resolve_runner',lambda repository:('test-runner:local',None))
    monkeypatch.setattr(issues,'fetch_issue',lambda url:dict(owner='example',repo='maths',number=42,title='Sum missing last integer',body='total(5) should be 15',url=url))
    def clone(root,*args):
        if args[0]=='clone':
            target=Path(args[-1]);target.mkdir()
            for source in repository.iterdir(): (target/source.name).write_text(source.read_text())
            return ''
        if args==('ls-files',):return 'maths.py\ntest_maths.py'
        return 'abc123'
    monkeypatch.setattr(issues,'git',clone)
    def cached(repository,target,ref=None):
        clone(target.parent,'clone',str(target))
        return {'commit':'abc123','cache_hit':True}
    monkeypatch.setattr(issues,'checkout_source',cached)
    def model(model,messages,structured=False):
        if 'brief source-grounded analysis' in messages[-1]['content']:
            return json.dumps({'plan':'Fix inclusive sum in maths.py','test_paths':['test_maths.py']})
        return json.dumps({'actions':[{'tool':'write_file','path':'maths.py','content':'def total(n):\n    return sum(range(n + 1))\n'}]})
    monkeypatch.setattr(issues,'chat',model)
    def run(tools):
        if 'n + 1' in tools.read_file('maths.py'):
            return dict(code=0,output='1 passed',executed=1,errors=0)
        return baseline
    monkeypatch.setattr(issues.RepoTools,'run_tests',run)


def test_issue_flow_uses_actual_report_source_and_tests(repository,monkeypatch):
    configure_flow(repository,monkeypatch,dict(code=1,output='assert 10 == 15',executed=1,errors=0))
    events=list(issues.repair_issue('https://github.com/example/maths/issues/42'))
    assert next(e for e in events if e['kind']=='issue')['issue']['title']=='Sum missing last integer'
    assert any(e['kind']=='edited' and e['path']=='maths.py' for e in events)
    assert events[-1]['success'] and 'a/maths.py' in events[-1]['diff']
    assert events[-1]['commit']=='abc123'
    assert 'job_id' not in events[-1]  # no demo publishing destination may be used

@pytest.mark.parametrize('baseline',[
    dict(code=0,output='1 passed',executed=1,errors=0),
    dict(code=5,output='no tests',executed=0,errors=0),
    dict(code=1,output='collection error',executed=1,errors=1),
])
def test_non_reproduction_never_claims_fix(repository,monkeypatch,baseline):
    configure_flow(repository,monkeypatch,baseline)
    events=list(issues.repair_issue('https://github.com/example/maths/issues/42'))
    assert events[-1]['success'] is False
    assert not any(e['kind']=='edited' for e in events)


def test_generated_regression_is_frozen_and_in_patch(repository):
    tools=issues.RepoTools(repository)
    name=tools.add_regression('def test_reported_behavior():\n    assert False\n')
    assert name in tools.files
    assert '/dev/null' in tools.diff()
    with pytest.raises(ValueError):tools.write_file(name,'def test_reported_behavior(): pass')
    with pytest.raises(issues.IssueError):tools.add_regression('def test_other(): pass')


def test_generated_regression_must_have_tests(repository):
    tools=issues.RepoTools(repository)
    with pytest.raises(issues.IssueError):tools.add_regression('print("no tests")')


def test_http_issue_route_never_calls_demo(monkeypatch):
    import io
    from email.message import Message
    from safefix import app
    seen=[]
    def real(url):
        seen.append(url)
        yield {'kind':'issue','issue':{'title':'Actual issue from GitHub'}}
        yield {'kind':'done','success':False,'message':'Not reproduced'}
    def demo(*args):raise AssertionError('Issue request used hardcoded demo')
    monkeypatch.setattr(app,'repair_issue',real)
    monkeypatch.setattr(app,'repair',demo)
    handler=app.Handler.__new__(app.Handler)
    handler.path='/repair'
    body=json.dumps({'issue':'https://github.com/owner/project/issues/42','mode':'live','demo':'bug1_offbyone'}).encode()
    handler.headers=Message();handler.headers['Content-Length']=str(len(body))
    handler.rfile=io.BytesIO(body);handler.wfile=io.BytesIO()
    handler.send_response=lambda *args:None
    handler.send_header=lambda *args:None
    handler.end_headers=lambda:None
    handler.do_POST()
    events=[json.loads(line) for line in handler.wfile.getvalue().splitlines()]
    assert seen==['https://github.com/owner/project/issues/42']
    assert events[0]['workflow']=='issue'
    assert events[1]['issue']['title']=='Actual issue from GitHub'
    assert 'demo' not in events[0]


def test_real_issue_plan_streams_before_build_finishes(repository,monkeypatch):
    import threading
    configure_flow(repository,monkeypatch,dict(code=1,output='assert 10 == 15',executed=1,errors=0))
    release=threading.Event();test_calls=[]
    original=issues.RepoTools.run_tests
    def run(tools):
        test_calls.append(1)
        assert release.is_set(),'Tests ran before environment readiness'
        return original(tools)
    def building(repository,ref=None,stop=None,existing=None):
        yield {'kind':'environment_log','message':'real dependency preparation in progress'}
        assert release.wait(3),'Planning did not overlap environment preparation'
        return ('prepared:local',ref)
    monkeypatch.setattr(issues.RepoTools,'run_tests',run)
    monkeypatch.setattr(issues,'prepare_environment',building)
    job=issues.repair_issue('https://github.com/example/maths/issues/42')
    seen=[]
    try:
        for event in job:
            seen.append(event)
            if event['kind']=='plan':
                assert not test_calls
                assert not release.is_set()
                release.set()
        assert seen[-1]['success']
        assert test_calls
    finally:
        release.set();job.close()
