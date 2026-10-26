"""One-use, loopback-only Aruba SMTP setup. Never logs submitted credentials."""
import argparse,base64,html,json,os,re,secrets,smtplib,tempfile,urllib.parse
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from cloud.service import send_email

def aruba_settings(address,password):
 address=address.strip()
 if not re.fullmatch(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',address):raise ValueError('Indirizzo email non valido.')
 if not password or len(password)>512 or '\n' in password or '\r' in password:raise ValueError('Inserisci la password della casella.')
 host='smtp.aruba.it' if address.lower().endswith(('@aruba.it','@technet.it')) else 'smtps.aruba.it'
 return {'SMTP_HOST':host,'SMTP_PORT':'465','SMTP_SECURITY':'ssl','SMTP_USER':address,'ALERT_FROM':address,'SMTP_PASSWORD':'','SMTP_PASSWORD_B64':base64.b64encode(password.encode()).decode()}

def save_settings(path,settings):
 text=path.read_text()
 for key,value in settings.items():
  line=key+'='+value
  text=re.sub(r'^'+re.escape(key)+r'=.*$',lambda m:line,text,flags=re.M) if re.search(r'^'+re.escape(key)+r'=',text,re.M) else text.rstrip()+'\n'+line+'\n'
 fd,name=tempfile.mkstemp(dir=path.parent,prefix='.mail-config-')
 try:
  with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
  os.chmod(name,0o600);os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
 token=secrets.token_urlsafe(32);origin='http://127.0.0.1:18081';completed=False
 for line in (args.runtime/'.env').read_text().splitlines():
  if '=' in line and not line.startswith('#'):
   k,v=line.split('=',1);os.environ[k]=v
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def allowed(self):return self.headers.get('Host')=='127.0.0.1:18081'
  def page(self,message='',error=False):
   form='' if completed else f'''<p>Usiamo la tua casella Aruba per gli avvisi del bot. Le credenziali restano nei file privati su questo Mac.</p><form method="post" action="/configure"><input type="hidden" name="csrf" value="{token}"><label>Indirizzo della casella Aruba<input name="address" type="email" autocomplete="username" required></label><label>Password della casella<input name="password" type="password" autocomplete="current-password" required maxlength="512"></label><button>Salva su questo Mac e invia l'email di prova</button></form><p>Il test viene inviato al tuo indirizzo di notifica già configurato. Non inserire le credenziali in chat.</p>'''
   body=('''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Notifiche email · Immoby</title><style>body{font:17px/1.55 system-ui;background:#f5f5f3;color:#192c30;margin:0;padding:36px 18px}main{max-width:560px;margin:auto;background:white;padding:28px;border-radius:16px}h1{font-size:27px}label{display:block;margin:18px 0}input{box-sizing:border-box;display:block;width:100%;padding:13px;margin-top:5px;font:inherit;border:1px solid #bcc5c4;border-radius:7px}button{font:inherit;background:#183e42;color:white;border:0;border-radius:7px;padding:14px;width:100%;cursor:pointer}.message{background:#e9f1ee;padding:15px;border-radius:7px}</style><main><h1>Notifiche email Immoby</h1>'''+('<p class="message">'+html.escape(message)+'</p>' if message else '')+form+'</main></html>').encode()
   self.send_response(400 if error else 200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'");self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
  def do_GET(self):
   if not self.allowed() or self.path!='/':self.send_error(404);return
   self.page('Configurazione salvata. Il server di Aruba ha accettato il test; controlla la posta ricevuta.' if completed else '')
  def do_POST(self):
   nonlocal completed
   if completed or not self.allowed() or self.path!='/configure' or self.headers.get('Origin')!=origin:self.send_error(403);return
   try:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=4096:raise ValueError('Richiesta non valida.')
    fields=urllib.parse.parse_qs(self.rfile.read(length).decode(),strict_parsing=True)
    if not secrets.compare_digest(fields.get('csrf',[''])[0],token):self.send_error(403);return
    settings=aruba_settings(fields.get('address',[''])[0],fields.get('password',[''])[0]);os.environ.update(settings)
    send_email('smtp-setup:'+secrets.token_hex(16),{'kind':'setup_test','session':'immoby-guest-bot'})
    for root in {args.runtime,args.source}:save_settings(root/'.env',settings)
    completed=True
    status=args.source/'data/mail-setup-status.json';status.write_text(json.dumps({'configured':True,'smtp_test_accepted':True,'inbox_receipt_verified':False}));status.chmod(0o600)
    self.page('Configurazione salvata. Il server di Aruba ha accettato il test; controlla la posta ricevuta.')
   except smtplib.SMTPAuthenticationError:self.page('Aruba non ha accettato le credenziali. Controlla indirizzo e password della casella.',True)
   except ValueError:self.page('Controlla indirizzo e password della casella.',True)
   except Exception:self.page('Il test non è riuscito. Le credenziali non sono state confermate. Riprova dopo la verifica della connessione.',True)
 HTTPServer(('127.0.0.1',18081),Handler).serve_forever()
if __name__=='__main__':main()
