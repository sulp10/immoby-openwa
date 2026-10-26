"""Vendor-neutral transports. No OpenAI endpoint or SDK dependency."""
import json,os,urllib.request,urllib.parse
PROFILES={
 'zai':('https://api.z.ai/api/paas/v4','glm-5.3-flash','ZAI_API_KEY'),
 'kimi':('https://api.moonshot.ai/v1','kimi-k3.1-pro','MOONSHOT_API_KEY'),
 'deepseek':('https://api.deepseek.com','deepseek-flash','DEEPSEEK_API_KEY'),
 'mistral_eu':('https://api.eu.mistral.ai/v1','zai-glm-5-3-flash','MISTRAL_API_KEY')}
class ChatClient:
 def __init__(self,provider='zai',key=None,transport=None):
  if provider not in PROFILES:raise ValueError('Unsupported provider')
  self.provider=provider;self.base,self.model,key_name=PROFILES[provider];self.key=key if key is not None else os.getenv(key_name,'');self.transport=transport or urllib.request.urlopen
 def complete(self,messages,*,model=None,max_tokens=4096,tools=None):
  if not self.key:raise RuntimeError('Model credentials not configured')
  payload={'model':model or self.model,'messages':messages,'max_tokens':min(max_tokens,8192),'stream':False,'reasoning_effort':'low'}
  if tools:payload.update(tools=tools,tool_choice='auto')
  else:payload['response_format']={'type':'json_object'}
  if self.provider=='zai':payload.update(thinking={'type':'enabled'},temperature=1)
  req=urllib.request.Request(self.base+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
  with self.transport(req,timeout=55) as response:data=json.load(response)
  choice=data['choices'][0]
  if choice.get('finish_reason') not in {'stop','tool_calls'}:raise ValueError('Incomplete or refused model result')
  # Preserve the complete assistant message, including reasoning and tool calls, in a tool loop.
  return choice['message'],data.get('usage',{})
 def check_model_availability(self):
  if not self.key:raise RuntimeError('Model credentials not configured')
  req=urllib.request.Request(self.base+'/models',headers={'Authorization':'Bearer '+self.key})
  with self.transport(req,timeout=20) as response:data=json.load(response)
  if self.model not in {x['id'] for x in data.get('data',[])}:raise RuntimeError('Selected model not available on this account or regional endpoint')
  return True

def nearby_search(kind,address,city,*,address_verified=False,key=None,transport=None):
 # The agent selects a category; it cannot replace the authenticated property's address.
 categories={'restaurants':'ristoranti','bars':'bar e caffè','luggage_storage':'deposito bagagli','parking':'parcheggio','attractions':'cosa vedere'}
 if not address_verified:raise PermissionError('Validated address required')
 if kind not in categories:raise ValueError('Unsupported local search category')
 token=key if key is not None else os.getenv('BRAVE_SEARCH_API_KEY','')
 if not token:raise RuntimeError('Web search credentials not configured')
 q=f'{categories[kind]} vicino {address}, {city}'
 url='https://api.search.brave.com/res/v1/web/search?'+urllib.parse.urlencode({'q':q,'count':5,'country':'IT','search_lang':'it'})
 req=urllib.request.Request(url,headers={'X-Subscription-Token':token,'Accept':'application/json'})
 with (transport or urllib.request.urlopen)(req,timeout=15) as response:data=json.load(response)
 return [{'title':r.get('title',''),'url':r.get('url',''),'snippet':r.get('description',''),'untrusted_external_evidence':True} for r in data.get('web',{}).get('results',[])[:5]]
