"""OpenWA 0.25.0 protocol, verified against commit 0fb74b28b2f85b6fbc013cefcc727072806c9b56."""
import hashlib,hmac,json,re,sqlite3,time,urllib.request,urllib.parse
MAX_BODY=1048576
EVENTS={'message.received','session.status','session.disconnected','session.qr','session.reconnect_loop','session.restriction'}
def verified_event(raw,signature,secret,allowed_sessions):
 if not secret or len(secret)<32:raise ValueError('Webhook secret must have at least 32 characters')
 if len(raw)>MAX_BODY:raise ValueError('Payload too large')
 expected='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
 if not isinstance(signature,str) or not re.fullmatch(r'sha256=[a-fA-F0-9]{64}',signature) or not hmac.compare_digest(signature,expected):raise PermissionError('Invalid signature')
 e=json.loads(raw)
 if not isinstance(e,dict) or e.get('sessionId') not in allowed_sessions:raise PermissionError('Unknown session')
 if e.get('event') not in EVENTS:raise ValueError('Event not subscribed')
 if not isinstance(e.get('data'),dict) or not isinstance(e.get('idempotencyKey'),str) or not e['idempotencyKey']:raise ValueError('Invalid envelope')
 if e['event']=='message.received':
  d=e['data']
  if d.get('fromMe') or d.get('isGroup') or str(d.get('from','')).endswith('@g.us'):return None
  if not isinstance(d.get('id'),str) or not isinstance(d.get('from'),str):raise ValueError('Missing message identity')
  if not isinstance(d.get('body',''),str) or len(d.get('body',''))>16000:raise ValueError('Invalid message text')
 return e
class Store:
 def __init__(self,path,disconnect_grace_seconds=300):
  if not isinstance(disconnect_grace_seconds,int) or not 0<=disconnect_grace_seconds<=3600:raise ValueError("Invalid disconnect grace")
  self.disconnect_grace_seconds=disconnect_grace_seconds
  self.db=sqlite3.connect(path,timeout=15);self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA busy_timeout=15000')
  self.db.executescript('''CREATE TABLE IF NOT EXISTS inbox(k TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',created REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS notices(k TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,created REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS monitor(session TEXT PRIMARY KEY,status TEXT NOT NULL,changed REAL NOT NULL,last_seen REAL NOT NULL,incident INTEGER NOT NULL DEFAULT 0,last_reminder REAL NOT NULL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS drafts(k TEXT PRIMARY KEY,payload TEXT NOT NULL,created REAL NOT NULL);''')
  if 'outage_since' not in {r[1] for r in self.db.execute('PRAGMA table_info(monitor)')}:
   try:self.db.execute('ALTER TABLE monitor ADD COLUMN outage_since REAL')
   except sqlite3.OperationalError:
    if 'outage_since' not in {r[1] for r in self.db.execute('PRAGMA table_info(monitor)')}:raise
 def accept(self,e,now=None):
  now=time.time() if now is None else now
  # Canonical key also collapses duplicates arriving through different webhook subscriptions.
  d=e['data'];key=e['sessionId']+':'+('message:'+d['id'] if e['event']=='message.received' else e['idempotencyKey'])
  with self.db:
   cur=self.db.execute('INSERT OR IGNORE INTO inbox(k,payload,created) VALUES (?,?,?)',(key,json.dumps(e),now))
  return key,cur.rowcount==1
 def notice(self,key,payload,now):
  with self.db:self.db.execute('INSERT OR IGNORE INTO notices(k,payload,created) VALUES (?,?,?)',(key,json.dumps(payload),now))
 def observe(self,session,status,*,now=None,reason='',reconnect_attempts=0):
  now=time.time() if now is None else now
  row=self.db.execute('SELECT status,changed,last_seen,incident,last_reminder,outage_since FROM monitor WHERE session=?',(session,)).fetchone()
  old,changed,last,incident,reminder,outage_since=row or ('unknown',now,now,0,now,None)
  if status=='ready':outage_since=None
  elif outage_since is None:outage_since=now
  if status!=old:
   changed=now
   if status!='ready' and old=='ready':incident+=1
  with self.db:self.db.execute('INSERT OR REPLACE INTO monitor(session,status,changed,last_seen,incident,last_reminder,outage_since) VALUES (?,?,?,?,?,?,?)',(session,status,changed,now,incident,reminder,outage_since))
  hard=bool(re.search(r'logout|logged.?out|unpaired|auth.?fail|relink',reason,re.I)) or status=='qr_ready'
  # Every state poll reuses the incident key; connectivity failures share a continuous five-minute grace.
  if status!='ready' and (hard or status=='action_required' or (outage_since is not None and now-outage_since>=self.disconnect_grace_seconds)):
   self.notice(f'session:{session}:{incident}:down',{'kind':'whatsapp_session_down','session':session,'status':status,'relink_required':hard,'reconnect_attempts':reconnect_attempts,'reason_category':'authentication' if hard else 'connectivity','contains_auth_material':False},now)
  if status=='ready' and old!='unknown' and now-changed>=60:
   down=f'session:{session}:{incident}:down'
   row=self.db.execute('SELECT state FROM notices WHERE k=?',(down,)).fetchone()
   if row and row[0]=='sent':self.notice(f'session:{session}:{incident}:recovered',{'kind':'whatsapp_session_recovered','session':session},now)
   # A delayed mail transport must not announce an outage after stable recovery.
   with self.db:
    self.db.execute("UPDATE notices SET state='resolved_before_delivery' WHERE state='pending' AND json_extract(payload,'$.session')=? AND json_extract(payload,'$.kind')='whatsapp_session_down'",(session,))
    for key, in self.db.execute("SELECT k FROM notices WHERE state='pending' AND json_extract(payload,'$.session')=? AND json_extract(payload,'$.kind')='whatsapp_session_recovered'",(session,)).fetchall():
     original=self.db.execute('SELECT state FROM notices WHERE k=?',(key.rsplit(':',1)[0]+':down',)).fetchone()
     if not original or original[0]!='sent':self.db.execute("UPDATE notices SET state='resolved_before_delivery' WHERE k=?",(key,))
  return {'status':status,'incident':incident,'needs_relink':hard}
 def weekly_phone_reminder(self,session,now=None):
  now=time.time() if now is None else now
  row=self.db.execute('SELECT last_reminder FROM monitor WHERE session=?',(session,)).fetchone()
  if not row:return
  if now-row[0]>=7*86400:
   self.notice(f'phone-check:{session}:{int(now//(7*86400))}',{'kind':'primary_phone_maintenance','session':session,'instruction':'Aprire WhatsApp sul telefono principale e controllare i dispositivi collegati. Non è una previsione di scadenza della sessione.'},now)
   with self.db:self.db.execute('UPDATE monitor SET last_reminder=? WHERE session=?',(now,session))
 def close(self):self.db.close()
class OpenWA:
 def __init__(self,base_url,api_key,session,transport=None):
  url=urllib.parse.urlsplit(base_url)
  if url.scheme!='https' and not(url.scheme=='http' and url.hostname in {'openwa-api','localhost','127.0.0.1'}):raise ValueError('HTTPS required outside private container transport')
  if not re.fullmatch(r'[A-Za-z0-9-]{1,128}',session):raise ValueError('Invalid session ID')
  self.base=base_url.rstrip('/');self.key=api_key;self.session=session;self.transport=transport or urllib.request.urlopen
 def request(self,path,body=None,key=None):
  headers={'X-API-Key':self.key,'Content-Type':'application/json'}
  if key:headers['Idempotency-Key']=hashlib.sha256(key.encode()).hexdigest()
  request=urllib.request.Request(self.base+'/api/sessions/'+self.session+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
  with self.transport(request,timeout=20) as response:return json.load(response)
 def status(self):return self.request('')
 def send_text(self,chat_id,text,key):return self.request('/messages/send-text',{'chatId':chat_id,'text':text,'linkPreview':False},key)
