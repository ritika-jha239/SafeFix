"""List available provider models without inference, using server-side credentials."""
import json
import os
import urllib.request
import urllib.error
from .providers import settings


def main():
    value=settings()
    key=os.getenv('TOKEN_FACTORY_API_KEY')
    if not key:raise SystemExit('TOKEN_FACTORY_API_KEY is not configured in this terminal; no request sent.')
    request=urllib.request.Request(value['base']+'/models',headers={
        'Authorization':'Bearer '+key,'User-Agent':'SafeFix/1.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:models=json.load(response)
    except urllib.error.HTTPError as e:raise SystemExit(f'{value["label"]} HTTP {e.code}; check provider access and account settings. No credential or response body printed.') from None
    except (urllib.error.URLError,TimeoutError):raise SystemExit('Provider could not be reached.') from None
    print(value['label']+' — available model IDs (no inference call made):')
    for model in models.get('data',[]):
        if isinstance(model,dict) and isinstance(model.get('id'),str):print(model['id'])
    for role in ('planner','repair'):
        selected=value[role]
        available=any(isinstance(m,dict) and m.get('id')==selected for m in models.get('data',[]))
        print(role+': '+(selected or 'NOT CONFIGURED')+(' [listed]' if available else ' [verify selection]'))

if __name__=='__main__':
    try:main()
    except ValueError as e:raise SystemExit(str(e)) from None
