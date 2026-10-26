import hashlib,hmac,json,tempfile,unittest
from pathlib import Path
from cloud.openwa import verified_event,Store,OpenWA
class Tests(unittest.TestCase):
 def event(self,**data):return {'event':'message.received','sessionId':'session-1','idempotencyKey':'key-wh1','data':{'id':'m1','from':'390000000000@c.us','body':'Wi-Fi?',**data}}
 def verify(self,e):
  raw=json.dumps(e).encode();secret='x'*40;sig='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest();return verified_event(raw,sig,secret,{'session-1'})
 def test_valid_signature(self):self.assertEqual(self.verify(self.event())['data']['id'],'m1')
 def test_rejects_tampered_body(self):
  with self.assertRaises(PermissionError):verified_event(b'{}','sha256=bad','x'*40,{'session-1'})
 def test_rejects_unsubscribed_session(self):
  e=self.event();e['sessionId']='other'
  with self.assertRaises(PermissionError):self.verify(e)
 def test_ignores_echoes_and_groups(self):
  self.assertIsNone(self.verify(self.event(fromMe=True)));self.assertIsNone(self.verify(self.event(isGroup=True)))
 def test_duplicate_messages_across_webhooks(self):
  with tempfile.TemporaryDirectory() as t:
   s=Store(str(Path(t)/'state'));e=self.event();self.assertTrue(s.accept(e)[1]);e['idempotencyKey']='key-wh2';self.assertFalse(s.accept(e)[1]);s.close()
 def test_disconnect_grace_and_email_dedup(self):
  s=Store(':memory:');s.observe('s','ready',now=100);s.observe('s','disconnected',now=110);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],0)
  s.observe('s','disconnected',now=410);s.observe('s','disconnected',now=500);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],1);s.close()
 def test_five_minute_boundary_and_status_changes(self):
  s=Store(':memory:');s.observe('s','ready',now=100);s.observe('s','disconnected',now=110);s.observe('s','initializing',now=200);s.observe('s','failed',now=409,reconnect_attempts=10)
  self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],0)
  s.observe('s','failed',now=410);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],1);s.close()
 def test_recovery_within_grace_creates_no_alert(self):
  s=Store(':memory:');s.observe('s','disconnected',now=100);s.observe('s','ready',now=399);s.observe('s','ready',now=460)
  self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],0);s.close()
 def test_logout_alert_without_wait(self):
  s=Store(':memory:');s.observe('s','qr_ready',reason='LOGOUT',now=100);notice=json.loads(s.db.execute('SELECT payload FROM notices').fetchone()[0]);self.assertTrue(notice['relink_required']);self.assertNotIn('qr',notice);s.close()
 def test_recovery_requires_stability(self):
  s=Store(':memory:');s.observe('s','failed',now=100);s.observe('s','failed',now=400);s.observe('s','ready',now=410);s.observe('s','ready',now=471);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],2);s.close()
 def test_maintenance_is_not_fake_expiry(self):
  s=Store(':memory:');s.observe('s','ready',now=100);s.weekly_phone_reminder('s',now=8*86400);s.weekly_phone_reminder('s',now=8*86400+60);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],1);s.close()
 def test_send_endpoint_and_idempotency(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self):return b'{"id":"message"}'
  seen=[]
  def transport(req,**kw):seen.append(req);return Response()
  c=OpenWA('http://openwa-api:2785','fake-test-key','session-1',transport);c.send_text('390000000000@c.us','test','event-key');self.assertTrue(seen[0].full_url.endswith('/messages/send-text'));self.assertIn('Idempotency-key',dict(seen[0].header_items()))
 def test_public_plain_http_refused(self):
  with self.assertRaises(ValueError):OpenWA('http://example.com','k','s')
if __name__=='__main__':unittest.main()
