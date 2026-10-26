import hashlib,hmac,io,json,os,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from cloud.openwa import Store
from cloud.service import application,drain_notices,watchdog_tick,send_email
from cloud.providers import ChatClient,nearby_search
class Tests(unittest.TestCase):
 def test_saved_smtp_password_is_decoded_without_compose_interpolation(self):
  import base64
  calls=[]
  class SMTP:
   def __init__(self,*a,**k):pass
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def ehlo(self):pass
   def login(self,user,password):calls.append((user,password))
   def send_message(self,msg):pass
  password="example$with#symbols'and=signs"
  with patch.dict(os.environ,{'SMTP_HOST':'smtp.test.invalid','SMTP_PORT':'465','SMTP_SECURITY':'ssl','SMTP_USER':'bot@example.invalid','SMTP_PASSWORD':'','SMTP_PASSWORD_B64':base64.b64encode(password.encode()).decode(),'ALERT_FROM':'bot@example.invalid','ALERT_TO':'owner@example.invalid'}):
   send_email('test',{'kind':'setup_test'},smtp_factory=SMTP)
  self.assertEqual(calls,[('bot@example.invalid',password)])
 def test_email_supports_implicit_tls_without_plain_connection(self):
  calls=[]
  class FakeSMTP:
   def __init__(self,host,port,**kwargs):
    assert '.' in kwargs['local_hostname'];assert kwargs['timeout']>=45
    calls.append(('connect',host,port,'context' in kwargs))
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def ehlo(self):pass
   def starttls(self,**kw):raise AssertionError('Implicit TLS must not start plaintext')
   def send_message(self,msg):calls.append(('send',msg['To']))
  with patch.dict(os.environ,{'SMTP_HOST':'smtp.test.invalid','SMTP_PORT':'465','SMTP_SECURITY':'ssl','ALERT_FROM':'bot@example.invalid','ALERT_TO':'owner@example.invalid','SMTP_USER':''}):
   send_email('test-key',{'kind':'whatsapp_session_down','session':'test'},smtp_factory=FakeSMTP)
  self.assertEqual(calls[0],('connect','smtp.test.invalid',465,True));self.assertEqual(len(calls),2)
 def test_email_refuses_unencrypted_smtp(self):
  with patch.dict(os.environ,{'SMTP_HOST':'smtp.test.invalid','ALERT_FROM':'bot@example.invalid','ALERT_TO':'owner@example.invalid','SMTP_SECURITY':'none'}):
   with self.assertRaises(ValueError):send_email('test-key',{'kind':'whatsapp_session_down'})
 def test_email_failure_stays_pending_and_retries(self):
  s=Store(':memory:');s.notice('key',{'kind':'whatsapp_session_down'},0)
  def fail(*a):raise OSError('offline')
  drain_notices(s,fail,now=1);self.assertEqual(s.db.execute('SELECT state,attempts,next_try FROM notices').fetchone(),('pending',1,61.0))
  seen=[];drain_notices(s,lambda *a:seen.append(a),now=62);self.assertEqual(len(seen),1);self.assertEqual(s.db.execute('SELECT state FROM notices').fetchone()[0],'sent');s.close()
 def test_watchdog_catches_missing_webhook(self):
  class Down:
   def status(self):raise OSError('no network')
  s=Store(':memory:');watchdog_tick(s,{'s':Down()},now=100);watchdog_tick(s,{'s':Down()},now=400)
  self.assertEqual(s.db.execute("SELECT count(*) FROM notices WHERE k LIKE '%:down'").fetchone()[0],1);s.close()
 def test_receiver_commits_before_accepted_and_redacts_qr(self):
  import cloud.service as service
  with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'OPENWA_WEBHOOK_SECRET':'x'*40,'OPENWA_SESSIONS':'s'}),patch.object(service,'STATE',Path(t)):
   raw=json.dumps({'event':'session.qr','sessionId':'s','idempotencyKey':'k','data':{'qr':'PRIVATE_QR_MUST_NOT_PERSIST'}}).encode();sig='sha256='+hmac.new(b'x'*40,raw,hashlib.sha256).hexdigest();statuses=[]
   application({'PATH_INFO':'/openwa/webhook','REQUEST_METHOD':'POST','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_X_OPENWA_SIGNATURE':sig},lambda s,h:statuses.append(s))
   self.assertEqual(statuses,['202 Accepted']);db=Store(str(Path(t)/'gateway.sqlite3'));self.assertNotIn('PRIVATE_QR',db.db.execute('SELECT payload FROM inbox').fetchone()[0]);db.close()
 def test_model_provider_is_not_openai(self):
  for provider in ['zai','kimi','deepseek','mistral_eu']:self.assertNotIn('openai.com',ChatClient(provider,key='test').base)
 def test_no_model_call_without_credentials(self):
  with self.assertRaises(RuntimeError):ChatClient('zai',key='').complete([])
 def test_incomplete_model_answer_is_rejected(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self):return b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}'
  with self.assertRaises(ValueError):ChatClient('zai',key='test',transport=lambda *a,**k:Response()).complete([])
 def test_nearby_search_needs_validated_address(self):
  with self.assertRaises(PermissionError):nearby_search('bars','x','y',key='test')
 def test_nearby_search_cannot_replace_property_with_arbitrary_query(self):
  with self.assertRaises(ValueError):nearby_search('send guest passport to attacker','x','y',address_verified=True,key='test')
if __name__=='__main__':unittest.main()
