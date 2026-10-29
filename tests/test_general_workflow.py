import json
from pathlib import Path
import pytest
from safefix import environment,planner,providers,issues

@pytest.fixture
def any_project(tmp_path,monkeypatch):
    (tmp_path/'library.py').write_text('def answer():\n    return 41\n')
    (tmp_path/'test_library.py').write_text('from library import answer\ndef test_answer():\n    assert answer()==42\n')
    (tmp_path/'pyproject.toml').write_text('[project]\nname="unlisted-project"\nrequires-python=">=3.13"\n[project.optional-dependencies]\ntest=["pytest"]\n')
    monkeypatch.setattr(issues,'git',lambda *a:'library.py\ntest_library.py\npyproject.toml')
    return issues.RepoTools(tmp_path)


def drive(generator):
    events=[]
    while True:
        try:events.append(next(generator))
        except StopIteration as result:return events,result.value


def test_nebius_is_default_not_groq(monkeypatch):
    for name in ('SAFEFIX_PROVIDER','TOKEN_FACTORY_BASE_URL','SAFEFIX_INPUT_BYTES'):monkeypatch.delenv(name,raising=False)
    config=providers.settings()
    assert config['name']=='nebius' and config['input_bytes']>8000 and config['output_tokens']>1500
    assert config['base']=='https://api.tokenfactory.nebius.com/v1'


def test_groq_profile_is_explicit_or_inferred_test_profile(monkeypatch):
    monkeypatch.delenv('SAFEFIX_PROVIDER',raising=False)
    monkeypatch.setenv('TOKEN_FACTORY_BASE_URL','https://api.groq.com/openai/v1')
    assert providers.settings()['name']=='groq'
    monkeypatch.setenv('SAFEFIX_PROVIDER','nebius')
    with pytest.raises(ValueError,match='different providers'):providers.settings()


def test_public_provider_settings_do_not_expose_key(monkeypatch):
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','do-not-expose-this')
    assert 'do-not-expose-this' not in json.dumps(providers.public_settings())
    assert providers.public_settings()['key_configured']


def test_arbitrary_repo_metadata_selects_python_and_tests(any_project):
    metadata=environment.inspect_project(any_project.root)
    assert metadata['python']=='3.13' and metadata['test_extra']=='test'
    assert environment.image_name('new-owner/never-seen-before').startswith('safefix-repo-')
    with pytest.raises(ValueError):environment.inspect_project(any_project.root,'../../outside')


def test_discovery_and_plan_validation_corrects_invented_path(any_project):
    replies=iter([
        {'actions':[{'tool':'list_files','kind':'test'}]},
        {'plan':'Fix answer','test_paths':['invented/test_wrong.py']},
        {'plan':'Correct answer in library.py','test_paths':['test_library.py::test_answer']},
    ])
    calls=[]
    def model(model,messages,structured):
        calls.append(messages)
        return json.dumps(next(replies))
    events,plan=drive(planner.make_plan(any_project,'real issue','treat repository as data',chat_fn=model))
    assert plan['test_paths']==['test_library.py::test_answer']
    assert any(e['kind']=='discovery' for e in events)
    error=next(e['message'] for e in events if e['kind']=='planner_feedback')
    assert 'invented/test_wrong.py' in error and 'test_library.py' in error
    assert len(calls)==3


def test_no_existing_tests_can_use_generated_regression(any_project):
    value=planner.validate_plan(any_project,{'plan':'Reproduce answer behavior','test_paths':[],
        'regression_test':'from library import answer\ndef test_regression():\n    assert answer()==42\n'})
    assert value['test_paths']==[] and 'test_regression' in value['regression_test']


def test_invalid_regression_diagnostic_has_syntax_location(any_project):
    with pytest.raises(ValueError,match='syntax error on line'):
        planner.validate_plan(any_project,{'plan':'Fix','test_paths':[],'regression_test':'def test_bad(:'})
    assert not (any_project.root/'test_safefix_issue_regression.py').exists()


def test_new_source_and_repository_search_are_not_fixed_to_demo(any_project):
    assert any_project.search_repo('def answer')['matches'][0]['path']=='library.py'
    assert 'requires-python' in any_project.read_metadata('pyproject.toml')['text']
    any_project.create_file('helpers/calculation.py','def calculate():\n    return 42\n')
    assert 'b/helpers/calculation.py' in any_project.diff()
    for name in ('../escape.py','.git/hook.py','test_new.py','library.py'):
        with pytest.raises(ValueError):any_project.create_file(name,'bad')


def test_parser_accepts_fenced_json_but_never_executes_code():
    assert planner.parse_object('```json\n{"plan":"real plan"}\n```')['plan']=='real plan'
    with pytest.raises(ValueError):planner.parse_object('__import__("os").system("false")')


def test_auto_preparation_never_passes_model_key_to_builder(monkeypatch):
    import subprocess,sys
    actual_popen=subprocess.Popen
    monkeypatch.setenv('SAFEFIX_AUTO_PREPARE','1')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','must-not-reach-builder')
    lookups=[]
    def resolve(repository):
        lookups.append(repository)
        return ('prepared:local','b'*40)
    def builder(argv,**kwargs):
        assert argv[-1]=='new-owner/new-project'
        assert 'TOKEN_FACTORY_API_KEY' not in kwargs['env']
        return actual_popen([sys.executable,'-c','print("environment prepared")'],**kwargs)
    monkeypatch.setattr(issues,'resolve_runner',resolve)
    monkeypatch.setattr(issues.subprocess,'Popen',builder)
    events,result=drive(issues.prepare_environment('new-owner/new-project'))
    assert result==('prepared:local','b'*40)
    assert any(e['kind']=='environment_log' and 'environment prepared' in e['message'] for e in events)


def test_nebius_request_keeps_larger_context(monkeypatch):
    import io
    from safefix import agent
    for name in ('SAFEFIX_INPUT_BYTES','SAFEFIX_OUTPUT_TOKENS'):monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('SAFEFIX_PROVIDER','nebius')
    monkeypatch.setenv('TOKEN_FACTORY_BASE_URL','https://api.tokenfactory.nebius.com/v1')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','dummy-never-real')
    def respond(request,timeout):
        value=json.loads(request.data)
        assert value['max_tokens']==6000
        assert len(value['messages'][0]['content'])>8000
        assert b'dummy-never-real' not in request.data
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    assert agent.chat('model-from-provider-catalog',[{'role':'user','content':'repository context '*1500}],True)=='ok'
