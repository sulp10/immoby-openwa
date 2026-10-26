"""Private local conversation simulator; never connects to live guest delivery."""
import html,json,os,re,secrets,sqlite3,threading,time,urllib.parse
from pathlib import Path
from cloud.agent import process_one
from cloud.openwa import Store
from cloud.policy import blocked_numbers,message_allowed
from cloud.providers import ChatClient
from core.controller import EXCLUDED

ROOT=Path(__file__).resolve().parent
def esc(value):return html.escape(str(value),quote=True)

class Sandbox:
 def __init__(self,state_dir,knowledge,catalog_path,client_factory=None):
  self.state=Path(state_dir);self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.knowledge=Path(knowledge);self.client_factory=client_factory or (lambda:ChatClient(os.getenv('MODEL_PROVIDER','zai')))
  self.csrf=secrets.token_urlsafe(32);self.locks={};self.guard=threading.Lock()
  self.catalog=[dict(x) for x in json.loads(Path(catalog_path).read_text()) if str(x['property_id']) not in EXCLUDED]
  counts={}
  if self.knowledge.exists():
   with sqlite3.connect('file:'+str(self.knowledge)+'?mode=ro',uri=True) as c:counts=dict(c.execute("SELECT property_id,count(*) FROM documents WHERE source_kind IN ('checkin','manual') AND COALESCE(json_extract(payload,'$.quarantined'),0)=0 GROUP BY property_id"))
  for row in self.catalog:row['documents']=counts.get(row['property_id'],0)
  db=self.database()
  db.db.executescript('''CREATE TABLE IF NOT EXISTS simulations(id TEXT PRIMARY KEY,property_id TEXT NOT NULL,suite_id TEXT,kind TEXT NOT NULL,access_enabled INTEGER NOT NULL,created REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS turns(run_id TEXT NOT NULL,message_id TEXT NOT NULL,guest_text TEXT NOT NULL,result TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(run_id,message_id));''');db.close()
 def database(self):return Store(str(self.state/'sandbox.sqlite3'))
 def start(self,property_id,suite_id,kind,access_enabled=True):
  if property_id not in {x['property_id'] for x in self.catalog}:raise ValueError('Immobile non disponibile.')
  if kind not in {'individual','group','excluded_number'}:raise ValueError('Tipo di mittente non valido.')
  if property_id=='3' and suite_id not in {'4','5','6','7'}:raise ValueError('Per Doria Tot scegli la suite da provare.')
  run=secrets.token_hex(16);db=self.database()
  try:
   if db.db.execute('SELECT count(*) FROM simulations WHERE created>?',(time.time()-86400,)).fetchone()[0]>=200:raise ValueError('Limite giornaliero di prove raggiunto.')
   with db.db:db.db.execute('INSERT INTO simulations VALUES (?,?,?,?,?,?)',(run,property_id,suite_id if property_id=='3' else None,kind,int(access_enabled),time.time()))
  finally:db.close()
  return run
 def ask(self,run,message,message_id=None):
  if os.getenv('APP_MODE')!='sandbox':raise PermissionError('Sandbox mode required')
  if not isinstance(message,str) or not message.strip() or len(message)>3000:raise ValueError('Scrivi un messaggio entro 3.000 caratteri.')
  message_id=message_id or secrets.token_hex(16)
  if not re.fullmatch('[a-f0-9]{32}',message_id):raise ValueError('Identificativo della prova non valido.')
  with self.guard:lock=self.locks.setdefault(run,threading.Lock())
  if not lock.acquire(blocking=False):raise ValueError('Attendi la risposta alla domanda precedente.')
  db=self.database()
  try:
   previous=db.db.execute('SELECT result FROM turns WHERE run_id=? AND message_id=?',(run,message_id)).fetchone()
   if previous:return json.loads(previous[0])
   row=db.db.execute('SELECT property_id,suite_id,kind,access_enabled,created FROM simulations WHERE id=?',(run,)).fetchone()
   if not row:raise ValueError('Avvia una nuova prova.')
   if db.db.execute('SELECT count(*) FROM turns WHERE run_id=?',(run,)).fetchone()[0]>=30 or db.db.execute('SELECT count(*) FROM turns WHERE created>?',(time.time()-3600,)).fetchone()[0]>=60:raise ValueError('Limite di prove raggiunto. Avvia una nuova prova più tardi.')
   pid,suite,kind,access,created=row;now=time.time();sender='390000000000@c.us'
   if kind=='group':sender='120300000000@g.us'
   elif kind=='excluded_number':
    blocked=sorted(blocked_numbers())
    if not blocked:raise ValueError('Numero escluso non configurato.')
    sender=blocked[0]+'@c.us'
   event={'event':'message.received','sessionId':'sandbox','idempotencyKey':message_id,'data':{'id':message_id,'from':sender,'body':message.strip(),'isGroup':kind=='group'}}
   key,_=db.accept(event)
   binding={'verified_by_sandbox_operator':True,'reservation_id':'sandbox-'+run,'property_id':pid,'assigned_suite_id':suite,'status':'confirmed','support_from':created-1,'support_until':created+86400,'access_release_from':created-1 if access else created+86400,'access_release_until':created+86400}
   try:
    client=self.client_factory() if message_allowed(event['data']) else None
    result=process_one(db,key,event,client,{'sandbox:'+sender:binding},self.knowledge,now=now,simulation=True,property_catalog=self.catalog)
   except Exception as error:
    # A failed test is visible locally, never delivered to an operator or guest.
    result={'status':'test_error','automatic_send':False,'error_type':type(error).__name__,'error_detail':str(error)[:200],'guest_reply':'La prova non è riuscita. Puoi riprovare o scegliere un altro immobile.'}
   with db.db:db.db.execute('INSERT INTO turns VALUES (?,?,?,?,?)',(run,message_id,message.strip(),json.dumps(result),now))
   return result
  finally:db.close();lock.release()
 def render(self,run='',error=''):
  db=self.database()
  try:
   selected=db.db.execute('SELECT property_id,suite_id,kind,access_enabled FROM simulations WHERE id=?',(run,)).fetchone() if run else None
   turns=db.db.execute('SELECT guest_text,result FROM turns WHERE run_id=? ORDER BY created',(run,)).fetchall() if selected else []
  finally:db.close()
  options=''.join('<option value="'+esc(x['property_id'])+'"'+(' selected' if selected and selected[0]==x['property_id'] else '')+'>'+esc(x['name']+' · '+x['property_id']+(' · fonte in verifica' if x.get('source_review_required') else '')+(' · istruzioni mancanti' if not x['documents'] and x['property_id']!='3' else ''))+'</option>' for x in self.catalog)
  def choices(items,current):return ''.join('<option value="'+esc(value)+'"'+(' selected' if value==current else '')+'>'+esc(label)+'</option>' for value,label in items)
  suites=choices([('','Scegli la suite'),('4','Doria Camera 1'),('5','Doria Camera 2'),('6','Doria Camera 3'),('7','Doria Camera 4')],selected[1] if selected else '')
  kinds=choices([('individual','Ospite singolo'),('excluded_number','Numero escluso'),('group','Gruppo WhatsApp')],selected[2] if selected else 'individual')
  phases=choices([('access','Check-in autorizzato (simulazione)'),('before','Prima dell’orario di accesso')],'before' if selected and not selected[3] else 'access')
  csrf='<input type="hidden" name="csrf" value="'+self.csrf+'">'
  cards=[]
  for guest,raw in turns:
   result=json.loads(raw);draft=result.get('draft',{})
   reply=draft.get('guest_reply') or result.get('guest_reply','')
   if result['status']=='inhibited':reply='Messaggio escluso: il modello non è stato chiamato e non è stata preparata alcuna risposta.'
   route=result.get('controller',{}).get('route','');attempts=result.get('controller',{}).get('failed_attempts',0)
   meta='Bloccato' if result['status']=='inhibited' else 'Prova non riuscita' if result['status']=='test_error' else 'Bozza · '+str(draft.get('language',''))
   if draft.get('requires_operator') or (route and route not in {'assist','resolved'}):meta+=' · intervento operatore simulato'
   if result.get('property_location_check',{}).get('status') not in {None,'confirmed'}:meta+=' · immobile da confermare'
   if attempts:meta+=' · tentativi falliti: '+str(attempts)
   cards.append('<article class="turn"><div class="guest"><small>Ospite simulato</small><p>'+esc(guest)+'</p></div><div class="reply"><small>'+esc(meta)+'</small><p>'+esc(reply)+'</p></div></article>')
  composer='<p class="empty">Scegli un immobile e avvia una prova. Puoi scrivere nella lingua che preferisci.</p>'
  if selected:
   name=next(x['name'] for x in self.catalog if x['property_id']==selected[0])
   composer=('<div class="conversation-title"><h2>'+esc(name)+'</h2><span>'+('Accesso simulato autorizzato' if selected[3] else 'Prima dell’orario di accesso')+'</span></div>'+''.join(cards)+
    '<form method="post" action="/ask" class="composer">'+csrf+'<input type="hidden" name="run_id" value="'+esc(run)+'"><input type="hidden" name="message_id" value="'+secrets.token_hex(16)+'"><label for="message">Messaggio dell’ospite</label><textarea id="message" name="message" maxlength="3000" rows="3" placeholder="Ad esempio: sono davanti al portone, come entro?" required></textarea><button type="submit">Prova la risposta</button><p class="busy" role="status" hidden>Sto preparando la risposta…</p></form>')
  return ('''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prova il bot · Immoby</title><link rel="stylesheet" href="/sandbox.css"><script defer src="/sandbox.js"></script></head><body><header><div class="brand">IMMOBY <span>Assistenza ospiti</span></div><div class="badge">Ambiente di prova</div></header><main><section class="intro"><h1>Proviamo le risposte, immobile per immobile.</h1><p>Scrivi come farebbe un ospite e controlla la risposta. Le prove usano le istruzioni importate da KrossBooking.</p><div class="status"><span>Gruppi esclusi</span><span>Numero escluso protetto</span><span>Invii WhatsApp ed email disattivati</span></div></section>'''+
   ('<p class="error" role="alert">'+esc(error)+'</p>' if error else '')+
   '<div class="layout"><aside><h2>Nuova prova</h2><form method="post" action="/start">'+csrf+'<label for="property">Immobile</label><select id="property" name="property_id">'+options+'</select><label for="suite">Suite (solo Doria Tot)</label><select id="suite" name="suite_id">'+suites+'</select><label for="kind">Mittente da simulare</label><select id="kind" name="kind">'+kinds+'</select><label for="phase">Fase del soggiorno</label><select id="phase" name="phase">'+phases+'</select><button type="submit">Avvia nuova prova</button></form><p class="note">Avvia una nuova prova per verificare gli ultimi aggiornamenti. Ogni prova parte da una conversazione vuota. Le richieste di intervento sono simulate: nessuna notifica viene inviata.</p><p class="note">Non è collegata a prenotazioni reali. Le istruzioni importate devono ancora essere validate per l’invio automatico.</p></aside><section class="conversation" aria-label="Conversazione di prova">'+composer+'</section></div></main></body></html>').encode()
 def __call__(self,environ,start_response):
  path=environ.get('PATH_INFO','/');method=environ.get('REQUEST_METHOD','GET');headers=[('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','same-origin'),('Content-Security-Policy',"default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'")]
  if environ.get('HTTP_HOST')!='127.0.0.1:18082':start_response('403 Forbidden',headers);return [b'Forbidden']
  if method=='GET' and path in {'/sandbox.css','/sandbox.js'}:
   body=(ROOT/path[1:]).read_bytes();start_response('200 OK',headers+[('Content-Type','text/css' if path.endswith('.css') else 'text/javascript')]);return [body]
  if method=='GET' and path=='/':
   run=urllib.parse.parse_qs(environ.get('QUERY_STRING','')).get('run_id',[''])[0];body=self.render(run);start_response('200 OK',headers+[('Content-Type','text/html; charset=utf-8')]);return [body]
  if method!='POST' or path not in {'/start','/ask'}:start_response('404 Not Found',headers);return [b'Not found']
  if environ.get('HTTP_ORIGIN')!='http://127.0.0.1:18082':start_response('403 Forbidden',headers);return [b'Forbidden']
  try:
   length=int(environ.get('CONTENT_LENGTH','0'))
   if not 0<length<=16000:raise ValueError('Messaggio troppo lungo.')
   form=urllib.parse.parse_qs(environ['wsgi.input'].read(length).decode(),strict_parsing=True)
   if not secrets.compare_digest(form.get('csrf',[''])[0],self.csrf):start_response('403 Forbidden',headers);return [b'Forbidden']
   value=lambda key:form.get(key,[''])[0]
   if path=='/start':run=self.start(value('property_id'),value('suite_id'),value('kind'),value('phase')=='access')
   else:run=value('run_id');self.ask(run,value('message'),value('message_id'))
   start_response('303 See Other',headers+[('Location','/?'+urllib.parse.urlencode({'run_id':run}))]);return [b'']
  except (ValueError,PermissionError) as e:
   body=self.render(error=str(e));start_response('400 Bad Request',headers+[('Content-Type','text/html; charset=utf-8')]);return [body]

_app=None
def application(environ,start_response):
 global _app
 if os.getenv('APP_MODE')!='sandbox':start_response('503 Service Unavailable',[]);return [b'Sandbox only']
 if _app is None:_app=Sandbox(Path(os.environ['STATE_DIR']),Path(os.environ['KNOWLEDGE_DB']),Path(os.environ['PROPERTY_CATALOG']))
 return _app(environ,start_response)
