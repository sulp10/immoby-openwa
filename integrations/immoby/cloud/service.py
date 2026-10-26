"""Durable OpenWA receiver and independent email session watchdog.
This service does not enable guest auto-replies. Agent integration remains shadow.
"""
import json,os,smtplib,ssl,time
from email.message import EmailMessage
from pathlib import Path
from cloud.openwa import Store,OpenWA,verified_event,MAX_BODY
STATE=Path(os.getenv('STATE_DIR','data'));STATE.mkdir(exist_ok=True,parents=True,mode=0o700)
def sessions():return {s for s in os.getenv('OPENWA_SESSIONS','').split(',') if s}
def database():return Store(str(STATE/'gateway.sqlite3'),disconnect_grace_seconds=int(os.getenv('DISCONNECT_GRACE_SECONDS','300')))
def application(environ,start_response):
 status='200 OK';result={'service':'immoby-guest-bot','mode':'shadow'}
 try:
  if environ.get('PATH_INFO')=='/health' and environ.get('REQUEST_METHOD')=='GET':pass
  elif environ.get('PATH_INFO')=='/openwa/webhook' and environ.get('REQUEST_METHOD')=='POST':
   length=int(environ.get('CONTENT_LENGTH') or 0)
   if length<=0 or length>MAX_BODY:raise ValueError('Invalid length')
   raw=environ['wsgi.input'].read(length)
   if len(raw)!=length:raise ValueError('Incomplete request body')
   e=verified_event(raw,environ.get('HTTP_X_OPENWA_SIGNATURE'),os.getenv('OPENWA_WEBHOOK_SECRET',''),sessions())
   if e:
    if e['event']=='session.qr':e={**e,'data':{'status':'qr_ready'}} # never persist or email QR authentication material
    db=database()
    try:key,inserted=db.accept(e)
    finally:db.close()
    result={'accepted':True,'new':inserted}
   else:result={'accepted':True,'ignored':True}
   status='202 Accepted'
  else:status='404 Not Found';result={'error':'not_found'}
 except PermissionError:status='401 Unauthorized';result={'error':'unauthorized'}
 except (ValueError,TypeError,KeyError,UnicodeDecodeError):status='400 Bad Request';result={'error':'invalid_request'}
 except Exception:status='503 Service Unavailable';result={'error':'temporarily_unavailable'}
 body=json.dumps(result).encode();start_response(status,[('Content-Type','application/json'),('Content-Length',str(len(body))),('Cache-Control','no-store')]);return [body]

def send_email(key,notice,*,smtp_factory=None):
 host=os.getenv('SMTP_HOST','');sender=os.getenv('ALERT_FROM','');recipients=[x.strip() for x in os.getenv('ALERT_TO','').split(',') if x.strip()]
 if not host or not sender or not recipients:raise RuntimeError('Verified email sender and recipients must be configured')
 subjects={'whatsapp_session_down':'WhatsApp richiede attenzione','whatsapp_session_recovered':'WhatsApp è di nuovo collegato','primary_phone_maintenance':'Controllo periodico del telefono WhatsApp','guest_requires_operator':'Un ospite ha bisogno di assistenza'}
 kind=notice['kind'];message=EmailMessage();message['Subject']='Immoby · '+subjects.get(kind,'Avviso operativo');message['From']=sender;message['To']=', '.join(recipients)
 import hashlib
 message['Message-ID']='<'+hashlib.sha256(key.encode()).hexdigest()+'@immoby-alerts>'
 text=''
 if kind=='whatsapp_session_down':
  text='La sessione WhatsApp non è operativa. Le risposte automatiche potrebbero essere ferme. '
  text+='È necessario ricollegare il telefono dalla console protetta.' if notice.get('relink_required') else 'Il sistema sta verificando il collegamento; controlla la console protetta se il problema continua.'
 elif kind=='whatsapp_session_recovered':text='La sessione WhatsApp è di nuovo collegata e risulta stabile da almeno un minuto. Verifica nella console gli eventuali messaggi rimasti in attesa.'
 elif kind=='primary_phone_maintenance':text=notice['instruction']
 else:text='È richiesto l’intervento di un operatore. Controlla la console protetta per i dettagli.'
 message.set_content(text+'\n\nSessione: '+str(notice.get('session',''))+'\nNon sono inclusi QR, codici di accesso o dati personali degli ospiti.')
 port=int(os.getenv('SMTP_PORT','587'))
 security=os.getenv('SMTP_SECURITY','ssl' if port==465 else 'starttls')
 if security not in {'ssl','starttls'}:raise ValueError('Encrypted SMTP transport required')
 context=ssl.create_default_context()
 factory=smtp_factory or (smtplib.SMTP_SSL if security=='ssl' else smtplib.SMTP)
 kwargs={'timeout':20}
 if security=='ssl':kwargs['context']=context
 with factory(host,port,**kwargs) as smtp:
  smtp.ehlo()
  if security=='starttls':smtp.starttls(context=context);smtp.ehlo()
  if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
  smtp.send_message(message)

def drain_notices(store,send=send_email,now=None):
 now=time.time() if now is None else now
 rows=store.db.execute("SELECT k,payload,attempts FROM notices WHERE state='pending' AND next_try<=? ORDER BY created LIMIT 10",(now,)).fetchall()
 for key,raw,attempts in rows:
  try:send(key,json.loads(raw))
  except Exception:
   delay=min(60*2**min(attempts,6),3600)
   with store.db:store.db.execute('UPDATE notices SET attempts=attempts+1,next_try=? WHERE k=?',(now+delay,key))
  else:
   with store.db:store.db.execute("UPDATE notices SET state='sent',attempts=attempts+1 WHERE k=?",(key,))

def watchdog_tick(store,clients,now=None):
 now=time.time() if now is None else now
 # Webhooks complement polling; neither mechanism depends on an LLM.
 for key,raw in store.db.execute("SELECT k,payload FROM inbox WHERE state='pending' ORDER BY created LIMIT 100").fetchall():
  e=json.loads(raw);d=e['data'];event=e['event']
  if event.startswith('session.'):
   status=d.get('status')
   if event=='session.qr':status='qr_ready'
   elif event=='session.disconnected':status='disconnected'
   elif event=='session.reconnect_loop':status='disconnected'
   elif event=='session.restriction':status='action_required' if d.get('active') else None
   if status:store.observe(e['sessionId'],status,reason=str(d.get('reason','')),reconnect_attempts=int(d.get('attempts',0)),now=now)
   with store.db:store.db.execute("UPDATE inbox SET state='handled' WHERE k=?",(key,))
 for session,client in clients.items():
  try:
   response=client.status();row=response.get('data',response)
   if not isinstance(row,dict) or not isinstance(row.get('status'),str):raise ValueError('Unknown status response')
   store.observe(session,row['status'],reason=str(row.get('lastError','')),now=now)
  except Exception:store.observe(session,'api_unreachable',now=now)
  store.weekly_phone_reminder(session,now=now)

def main():
 if not sessions():raise RuntimeError('Configure the actual OpenWA session IDs')
 if not os.getenv('OPENWA_API_KEY'):raise RuntimeError('Configure the session-scoped operator API key')
 clients={s:OpenWA(os.getenv('OPENWA_BASE_URL','http://openwa-api:2785'),os.environ['OPENWA_API_KEY'],s) for s in sessions()}
 store=database()
 while True:
  watchdog_tick(store,clients);drain_notices(store);time.sleep(30)
if __name__=='__main__':main()
