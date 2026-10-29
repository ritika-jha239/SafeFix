"""Server-side provider profiles. Nebius is the production default."""
from urllib.parse import urlsplit
import os

PROVIDERS={
 'nebius':dict(label='Nebius Token Factory',base='https://api.tokenfactory.nebius.com/v1',input_bytes=64000,output_tokens=6000),
 'groq':dict(label='Groq · test provider',base='https://api.groq.com/openai/v1',input_bytes=8000,output_tokens=1500),
 'openai':dict(label='OpenAI',base='https://api.openai.com/v1',input_bytes=48000,output_tokens=4000),
 'custom':dict(label='Custom OpenAI-compatible API',base='',input_bytes=32000,output_tokens=4000),
}

def settings():
    base=os.getenv('TOKEN_FACTORY_BASE_URL','').rstrip('/')
    selected=os.getenv('SAFEFIX_PROVIDER','').lower()
    if not selected:
        host=urlsplit(base).hostname
        selected={'api.groq.com':'groq','api.openai.com':'openai','api.tokenfactory.nebius.com':'nebius'}.get(host,'custom' if base else 'nebius')
    if selected not in PROVIDERS:raise ValueError('SAFEFIX_PROVIDER must be nebius, groq, openai, or custom')
    if os.getenv('SAFEFIX_PROVIDER') and base:
        known={'api.groq.com':'groq','api.openai.com':'openai','api.tokenfactory.nebius.com':'nebius'}.get(urlsplit(base).hostname)
        if known and selected not in (known,'custom'):raise ValueError('SAFEFIX_PROVIDER and TOKEN_FACTORY_BASE_URL select different providers; update or unset the old base URL')
    result={'name':selected,**PROVIDERS[selected]}
    result['base']=base or result['base']
    parsed=urlsplit(result['base'])
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Provider base must be a credential-free HTTPS API URL')
    result['planner']=os.getenv('SAFEFIX_PLANNER_MODEL') or os.getenv('NEMOTRON_ULTRA_MODEL','')
    result['repair']=os.getenv('SAFEFIX_REPAIR_MODEL') or os.getenv('NEMOTRON_NANO_MODEL','')
    return result


def public_settings():
    value=settings()
    return {k:value[k] for k in ('name','label','base','planner','repair')} | {'key_configured':bool(os.getenv('TOKEN_FACTORY_API_KEY'))}
