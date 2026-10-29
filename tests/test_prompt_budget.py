import io
import json
import urllib.error
import pytest
from safefix import agent, issues
from safefix.prompts import bounded_messages, request_body


def test_serialized_payload_bounded_for_large_code_and_history():
    messages=[{'role':'system','content':'Repair actual repository source'}]
    for n in range(30):
        messages.append({'role':'user' if n%2 else 'assistant','content':('\\\"\nκώδικας '*10000)})
    body=request_body('model',messages,True,8000,1500)
    assert len(body)<=14000
    data=json.loads(body)
    assert len(data['messages'])<=5
    assert data['messages'][0]['content']=='Repair actual repository source'
    assert data['response_format']=={'type':'json_object'}


def test_413_retries_once_with_smaller_request_and_output(monkeypatch):
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','dummy')
    monkeypatch.setenv('TOKEN_FACTORY_BASE_URL','https://provider.example/v1')
    bodies=[]
    def provider(req,timeout):
        bodies.append(json.loads(req.data))
        if len(bodies)==1:
            raise urllib.error.HTTPError(req.full_url,413,'Too large',{},io.BytesIO())
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
    monkeypatch.setattr(agent.urllib.request,'urlopen',provider)
    assert agent.chat('model',[{'role':'user','content':'code '*10000}],True)=='ok'
    assert len(bodies)==2
    assert len(bodies[1]['messages'][0]['content'])<len(bodies[0]['messages'][0]['content'])
    assert bodies[1]['max_tokens']<bodies[0]['max_tokens']


def test_repeated_413_has_actionable_error(monkeypatch):
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','dummy')
    monkeypatch.setenv('TOKEN_FACTORY_BASE_URL','https://provider.example/v1')
    calls=[]
    def provider(req,timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url,413,'secret body',{},io.BytesIO(b'secret'))
    monkeypatch.setattr(agent.urllib.request,'urlopen',provider)
    with pytest.raises(agent.ModelAPIError,match='SAFEFIX_INPUT_BYTES') as caught:agent.chat('model',[])
    assert len(calls)==2 and 'secret' not in str(caught.value)


def test_large_source_supports_targeted_reads_and_replacements(tmp_path,monkeypatch):
    text='# filler\n'*12000+'def relevant():\n    return 1\n'
    (tmp_path/'module.py').write_text(text)
    (tmp_path/'test_module.py').write_text('def test_value(): pass')
    monkeypatch.setattr(issues,'git',lambda *a:'module.py\ntest_module.py')
    tools=issues.RepoTools(tmp_path)
    window=tools.read_lines('module.py',12001,12002)
    assert 'return 1' in window['text'] and len(window['text'])<2600
    tools.edit_file('module.py','    return 1','    return 2')
    assert '+    return 2' in tools.diff()
    with pytest.raises(ValueError):tools.edit_file('test_module.py','pass','assert True')
    with pytest.raises(ValueError):tools.edit_file('module.py','# filler','# changed')
    tools.select_tests(['test_module.py::test_value'])
    assert tools.tests==['test_module.py::test_value']


def test_compact_context_does_not_dump_repository(tmp_path,monkeypatch):
    monkeypatch.setenv('SAFEFIX_PROVIDER','groq')
    paths=[]
    for n in range(80):
        path=f'test_component_{n}.py'
        (tmp_path/path).write_text('def target():\n    return 1\n'+'# padded code\n'*500)
        paths.append(path)
    monkeypatch.setattr(issues,'git',lambda *a:'\n'.join(paths))
    tools=issues.RepoTools(tmp_path)
    value=issues.context(tools,{'title':'target returns incorrect value','body':'Details\n```python\nassert target()==2\n```'+' x'*50000,'url':'https://github.com/a/b/issues/1'})
    assert len(value.encode())<=4800
    parsed=json.loads(value)
    assert len(parsed['python_paths'])<=30
    assert 1<=len(parsed['source_excerpts'])<=2
    assert 'assert target()==2' in parsed['issue']['reproduction']


def test_scientific_runner_rejects_wrong_revision_metadata(monkeypatch):
    from types import SimpleNamespace
    def inspect(*args,**kwargs):
        return SimpleNamespace(stdout=json.dumps({'safefix.repository':'wrong/repo','safefix.commit':'a'*40}))
    monkeypatch.setattr(issues.subprocess,'run',inspect)
    with pytest.raises(issues.IssueError,match='does not match'):
        issues.scientific_revision('pandas-dev/pandas','safefix-pandas:local')


def test_scientific_runner_pins_exact_commit(monkeypatch):
    from types import SimpleNamespace
    def inspect(*args,**kwargs):
        return SimpleNamespace(stdout=json.dumps({'safefix.repository':'pandas-dev/pandas','safefix.commit':'a'*40}))
    monkeypatch.setattr(issues.subprocess,'run',inspect)
    assert issues.scientific_revision('pandas-dev/pandas','safefix-pandas:local')=='a'*40


def test_searches_find_symbols_without_returning_whole_large_file(tmp_path,monkeypatch):
    text='# padding\n'*15000+'def target_symbol():\n    return 42\n'
    (tmp_path/'module.py').write_text(text)
    monkeypatch.setattr(issues,'git',lambda *a:'module.py')
    tools=issues.RepoTools(tmp_path)
    result=tools.search_file('module.py','def target_symbol')
    assert result['matches']==1 and 'target_symbol' in result['excerpts']
    assert len(result['excerpts'].encode())<3000
