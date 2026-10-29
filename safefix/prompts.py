"""Bounded model context, independent of repository size and iteration count."""
import json
import os


def limit(name, default, low, high):
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def clip(text, size):
    data=str(text).encode('utf-8')
    if len(data)<=size:return str(text)
    marker=b'\n[... context truncated; request a targeted line range ...]\n'
    room=max(0,size-len(marker))
    head=room*2//3
    return data[:head].decode('utf-8',errors='ignore')+marker.decode()+data[-(room-head):].decode('utf-8',errors='ignore') if room else marker[:size].decode(errors='ignore')


def bounded_messages(messages, budget=8000):
    # Keep original task and latest feedback. Full old model outputs are expendable.
    system=next((m for m in messages if m['role']=='system'),None)
    other=[m for m in messages if m['role']!='system']
    if len(other)>4:other=[other[0],*other[-3:]]
    retained=([system] if system else [])+other
    if not retained:return []
    weights=[1 if m['role'] in ('system','assistant') else 3 for m in retained]
    total=sum(weights)
    return [{'role':m['role'],'content':clip(m['content'],max(100,budget*w//total))} for m,w in zip(retained,weights)]


def request_body(model,messages,structured,budget,output_tokens):
    result={'model':model,'messages':bounded_messages(messages,budget),'temperature':0.2,'max_tokens':output_tokens}
    if structured:result['response_format']={'type':'json_object'}
    # Bound the actual serialized payload, including JSON escaping, too.
    raw=json.dumps(result,ensure_ascii=False).encode()
    while len(raw)>14000 and budget>1000:
        budget//=2
        result['messages']=bounded_messages(messages,budget)
        raw=json.dumps(result,ensure_ascii=False).encode()
    return raw
