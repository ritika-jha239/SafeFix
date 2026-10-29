"""Repository discovery and recoverable plan validation; never execute code here."""
import ast
import json
import re
from .agent import chat
from .prompts import clip,limit
from .providers import settings

class PlanError(RuntimeError):
    pass

READ_TOOLS='list_files(query, kind=all|source|test|metadata, cursor), search_repo(query,kind), read_file(path,start_line,end_line), search_file(path,query), read_metadata(path)'


def parse_object(reply):
    if not isinstance(reply,str):raise ValueError('Expected a JSON object, received non-text content')
    text=reply.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text,flags=re.I)
        text=re.sub(r'\s*```$','',text)
    try:value=json.loads(text)
    except json.JSONDecodeError as e:raise ValueError(f'Invalid JSON at line {e.lineno}, column {e.colno}; return one JSON object without commentary') from None
    if not isinstance(value,dict):raise ValueError('Expected a JSON object, not a list or scalar')
    return value


def validate_plan(tools,value):
    if not isinstance(value.get('plan'),str) or not value['plan'].strip():raise ValueError('Missing nonempty plan string')
    paths=value.get('test_paths',[])
    if not isinstance(paths,list) or len(paths)>5:raise ValueError('test_paths must be a list of at most five real test selectors')
    content=value.get('regression_test')
    if content is not None and not isinstance(content,str):raise ValueError('regression_test must be Python source text or null')
    if content:
        if len(content.encode())>20000:raise ValueError('Regression source exceeds 20KB')
        try:tree=ast.parse(content)
        except SyntaxError as e:raise ValueError(f'Regression Python syntax error on line {e.lineno}: {e.msg}') from None
        if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree)):
            raise ValueError('Regression must contain a pytest test_ function or unittest test_ method')
    if not paths and not content:raise ValueError('Provide existing test_paths, an issue-specific regression_test, or both; no tests were selected')
    if paths:
        try:tools.select_tests(paths)
        except (ValueError,RuntimeError) as e:
            actual=tools.list_files(kind='test')['paths'][:12]
            raise ValueError(f'Invalid test selection: {e}. Actual test files include: '+json.dumps(actual)) from None
    return {'plan':value['plan'],'test_paths':paths,'regression_test':content}


def read_action(tools,action):
    if not isinstance(action,dict):raise ValueError('Each tool action must be an object')
    name=action.get('tool')
    if name=='list_files':return tools.list_files(action.get('query',''),action.get('kind','all'),action.get('cursor',0))
    if name=='search_repo':return tools.search_repo(action['query'],action.get('kind','all'))
    if name=='read_file':return tools.read_lines(action['path'],action.get('start_line',1),action.get('end_line'))
    if name=='search_file':return tools.search_file(action['path'],action['query'])
    if name=='read_metadata':return tools.read_metadata(action['path'])
    raise ValueError('Planning only allows repository reads/searches; unsupported tool: '+str(name))


def make_plan(tools,material,system,chat_fn=None):
    profile=settings()
    budget=limit('SAFEFIX_INPUT_BYTES',profile['input_bytes'],2000,262144)
    prompt=('Inspect the real repository before choosing tests. Return either '
        '{"actions":[{"tool":"list_files","kind":"test","query":"relevant term"}]} '
        'to explore (up to six reads/searches), or a final JSON '
        '{"plan":"brief source-grounded analysis and test strategy","test_paths":["existing/test_file.py::test_name"],'
        '"regression_test":"complete pytest source reproducing the issue, or null"}. '
        'Never invent test paths. test_paths may be empty if a generated regression covers a project with no existing tests. '
        'Use narrow test nodes for large suites. Regression imports and assertions must exercise the real package behavior. '
        'No network, credentials or shell commands. The regression freezes before source repair. Available tools: '+READ_TOOLS+'\n'+material)
    base=[{'role':'system','content':system},{'role':'user','content':prompt}]
    feedback=[];last_error='No valid plan produced'
    for step in range(1,limit('SAFEFIX_PLAN_STEPS',8,2,20)+1):
        yield {'kind':'progress','stage':1,'message':f'Planner discovery/validation step {step} · {profile["label"]}'}
        messages=base+feedback
        reply=(chat_fn or chat)(profile['planner'],messages,True)
        try:
            value=parse_object(reply)
            if 'actions' in value:
                actions=value['actions']
                if not isinstance(actions,list) or not 1<=len(actions)<=6:raise ValueError('Exploration requires 1–6 tool actions')
                results=[]
                for action in actions:
                    try:
                        result=read_action(tools,action)
                        results.append({'tool':action.get('tool'),'result':result})
                        yield {'kind':'discovery','message':'Planner used '+str(action.get('tool')),'result':result}
                    except (ValueError,KeyError,TypeError,RuntimeError,UnicodeError) as e:
                        results.append({'error':str(e)})
                        yield {'kind':'planner_feedback','message':str(e),'attempt':step}
                feedback=[{'role':'assistant','content':clip(reply,1500)},
                          {'role':'user','content':clip(json.dumps(results,ensure_ascii=False),min(12000,budget//3))}]
                continue
            result=validate_plan(tools,value)
            return result
        except (ValueError,KeyError,TypeError) as e:
            last_error=str(e)
            yield {'kind':'planner_feedback','message':last_error,'attempt':step}
            feedback=[{'role':'assistant','content':clip(reply,1500)},
                      {'role':'user','content':'Plan validation failed: '+last_error+' Correct the JSON or use discovery tools to inspect actual paths. Do not invent names.'}]
    raise PlanError('Planner could not produce a valid plan after discovery/correction. Last validation error: '+last_error)
