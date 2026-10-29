from pathlib import Path
import pytest
from safefix.agent import DEMOS, repair
from safefix.sandbox import Tools

@pytest.mark.parametrize('demo', DEMOS)
def test_red_to_green(demo):
    source = Path('repos',demo,'solution.py').read_text()
    events = list(repair(demo))
    assert events[0]['code'] == 1
    assert events[-1]['success']
    assert 'diff' in events[-1]
    assert any(e['kind']=='tests_after' and e['code']==0 for e in events)
    assert Path('repos',demo,'solution.py').read_text() == source
    if demo.endswith('bait'):
        assert events[-1]['blocked']

def test_guardrails(tmp_path):
    tools = Tools(tmp_path)
    for path in ('../outside.py', '/etc/passwd'):
        with pytest.raises(ValueError): tools.read_file(path)
    with pytest.raises(ValueError): tools.write_file('test_solution.py','')
    with pytest.raises(ValueError): tools.command(['cat','~/.env'])
    (tmp_path/'solution.py').symlink_to('/tmp/outside.py')
    with pytest.raises(ValueError): tools.write_file('solution.py','bad')

def test_invalid_demo():
    with pytest.raises(ValueError): list(repair('../escape'))

def test_live_protocol_with_fake_provider(monkeypatch):
    import safefix.agent as agent
    calls = []
    def fake_chat(model, messages, structured=False):
        calls.append((model, structured))
        if not structured: return 'Fix inclusive boundary'
        return __import__('json').dumps({'actions':[{'tool':'write_file','path':'solution.py','content':agent.FIXES['bug1_offbyone']}]})
    monkeypatch.setenv('NEMOTRON_ULTRA_MODEL','planner')
    monkeypatch.setenv('NEMOTRON_NANO_MODEL','repair')
    monkeypatch.setattr(agent,'chat',fake_chat)
    assert list(agent.repair('bug1_offbyone','live'))[-1]['success']
    assert calls == [('planner', False), ('repair', True)]

@pytest.mark.parametrize('url', ['https://github.com/owner/repo/issues/42', ''])
def test_issue_context(url):
    from safefix.app import validate_issue
    assert validate_issue(url) == url

@pytest.mark.parametrize('url', ['https://evil.example/issues/42', 'file:///etc/passwd', 'https://github.com/a/b/issues/1?redirect=bad', None])
def test_issue_context_rejected(url):
    from safefix.app import validate_issue
    with pytest.raises(ValueError): validate_issue(url)
