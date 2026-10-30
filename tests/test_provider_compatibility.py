"""Provider JSON-mode recovery must remain bounded and keep errors private."""
import io
import json
import urllib.error

import pytest

from safefix import agent
from safefix.planner import parse_object


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('SAFEFIX_PROVIDER','groq')
    monkeypatch.setenv('TOKEN_FACTORY_BASE_URL','https://api.groq.com/openai/v1')
    monkeypatch.setenv('TOKEN_FACTORY_API_KEY','test-secret-not-real')


def failed(status, details):
    return urllib.error.HTTPError('https://api.groq.com/openai/v1/chat/completions',
        status,'private error text',{},io.BytesIO(json.dumps({'error':details}).encode()))


@pytest.mark.parametrize('details',[
    {'code':'json_validate_failed','message':'Failed to generate JSON','failed_generation':'private source'},
    {'code':'unsupported_parameter','param':'response_format'},
    {'message':'response_format is not supported by this model'},
])
def test_json_rejection_retries_without_enforcement(provider,monkeypatch,details):
    bodies=[]
    messages=[{'role':'user','content':'Inspect actual source and return JSON actions.'}]
    def respond(req,timeout):
        body=json.loads(req.data)
        bodies.append(body)
        if len(bodies)==1:raise failed(400,details)
        assert 'response_format' not in body
        assert 'actual source' in body['messages'][0]['content']
        assert 'valid JSON object' in body['messages'][-1]['content']
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"actions": []}'}}]}).encode())
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    assert parse_object(agent.chat('model',messages,True))=={'actions':[]}
    assert len(bodies)==2
    assert bodies[0]['response_format']=={'type':'json_object'}
    assert len(messages)==1  # caller history is not mutated


@pytest.mark.parametrize('statuses',[(413,400),(400,413)])
def test_size_and_json_retries_are_bounded_in_either_order(provider,monkeypatch,statuses):
    bodies=[]
    def respond(req,timeout):
        bodies.append(json.loads(req.data))
        status=statuses[min(len(bodies)-1,1)]
        raise failed(status,{'code':'json_validate_failed' if status==400 else 'other'})
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    with pytest.raises(agent.ModelAPIError):agent.chat('model',[],True)
    assert len(bodies)==3
    assert 'response_format' not in bodies[-1]
    assert bodies[-1]['max_tokens']<bodies[0]['max_tokens']


@pytest.mark.parametrize('status,details',[
    (400,{'code':'context_length_exceeded','param':'messages'}),
    (400,{'code':'unsupported_parameter','param':'temperature'}),
    (401,{'code':'json_validate_failed'}),
    (403,{'code':'json_validate_failed'}),
    (429,{'code':'json_validate_failed'}),
    (400,{'code':'test-secret-not-real','param':'private-source','message':'test-secret-not-real'}),
    (400,{'code':{},'param':[],'message':{}}),
])
def test_other_errors_not_retried_or_exposed(provider,monkeypatch,status,details):
    calls=[]
    def respond(req,timeout):
        calls.append(req)
        raise failed(status,details)
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    with pytest.raises(agent.ModelAPIError) as caught:agent.chat('model',[],True)
    error=str(caught.value)
    assert len(calls)==1
    assert 'test-secret-not-real' not in error and 'private' not in error
    if details.get('param')=='temperature':assert 'parameter=temperature' in error
    if details.get('code')=='context_length_exceeded':assert 'SAFEFIX_INPUT_BYTES' in error


def test_prompt_json_still_requires_valid_json(provider,monkeypatch):
    calls=[]
    def respond(req,timeout):
        calls.append(req)
        if len(calls)==1:raise failed(400,{'code':'json_validate_failed'})
        return io.BytesIO(b'{"choices":[{"message":{"content":"not JSON"}}]}')
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    with pytest.raises(ValueError,match='Invalid JSON'):
        parse_object(agent.chat('model',[],True))


def test_nonstructured_request_does_not_retry_json_errors(provider,monkeypatch):
    calls=[]
    def respond(req,timeout):
        calls.append(req)
        raise failed(400,{'code':'json_validate_failed'})
    monkeypatch.setattr(agent.urllib.request,'urlopen',respond)
    with pytest.raises(agent.ModelAPIError,match='code=json_validate_failed'):
        agent.chat('model',[],False)
    assert len(calls)==1
