import io,json,os,tempfile,unittest,urllib.parse
from pathlib import Path
from unittest.mock import patch
from cloud.agent import booking_for
from cloud.openwa import OpenWA
from cloud.service import send_email
from cloud.sandbox import Sandbox
class Tests(unittest.TestCase):
 def test_local_form_accepts_valid_csrf_and_rejects_foreign_origin(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'catalog.json';p.write_text(json.dumps([{'property_id':'8','name':'TEST'}]));app=Sandbox(root/'state',root/'db',p)
   seen=[];app({'HTTP_HOST':'127.0.0.1:18082','REQUEST_METHOD':'GET','PATH_INFO':'/'},lambda s,h:seen.append((s,dict(h))))
   self.assertEqual(seen[-1][1]['Referrer-Policy'],'same-origin')
   raw=urllib.parse.urlencode({'csrf':app.csrf,'property_id':'8','kind':'individual','phase':'access'}).encode()
   for origin,expected in [('http://127.0.0.1:18082','303'),('https://other.example','403'),('null','403')]:
    app({'HTTP_HOST':'127.0.0.1:18082','HTTP_ORIGIN':origin,'REQUEST_METHOD':'POST','PATH_INFO':'/start','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)},lambda s,h:seen.append((s,dict(h))))
    self.assertTrue(seen[-1][0].startswith(expected))
 def test_sandbox_cannot_send_whatsapp_or_email(self):
  with patch.dict(os.environ,{'APP_MODE':'sandbox'}):
   with self.assertRaises(PermissionError):OpenWA('http://openwa-api:2785','test','s').send_text('390000000000@c.us','test','id')
   with self.assertRaises(PermissionError):send_email('id',{'kind':'setup_test'})
 def test_simulated_bindings_are_never_accepted_in_production(self):
  event={'sessionId':'sandbox','data':{'from':'390000000000@c.us'}};binding={'verified_by_sandbox_operator':True,'status':'confirmed','reservation_id':'simulation','property_id':'8','support_from':0,'support_until':200};bindings={'sandbox:390000000000@c.us':binding}
  self.assertIsNone(booking_for(event,bindings,now=100))
  self.assertIsNotNone(booking_for(event,bindings,now=100,simulation=True))
 def test_catalog_excludes_retired_properties_and_no_model_for_inhibited_sender(self):
  def no_model():raise AssertionError('Must not reach model')
  with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'APP_MODE':'sandbox','BOT_BLOCKED_PHONES':'390001234567'}):
   root=Path(t);catalog=root/'catalog.json';catalog.write_text(json.dumps([{'property_id':'8','name':'TEST','guide_ids':['g']},{'property_id':'40','name':'EXCLUDED'}]))
   app=Sandbox(root/'state',root/'not-needed.sqlite',catalog,client_factory=no_model)
   self.assertEqual([x['property_id'] for x in app.catalog],['8'])
   for kind in ['group','excluded_number']:
    run=app.start('8','',kind);result=app.ask(run,'test')
    self.assertEqual(result['status'],'inhibited');self.assertFalse(result['automatic_send'])
 def test_doria_requires_suite_and_property_cannot_be_supplied_by_guest_text(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'catalog.json';p.write_text(json.dumps([{'property_id':'3','name':'DORIA TOT'}]));app=Sandbox(root/'state',root/'db',p)
   with self.assertRaises(ValueError):app.start('3','','individual')
   with self.assertRaises(ValueError):app.start('40','','individual')
   run=app.start('3','6','group',False);page=app.render(run).decode()
   for option in ['6','group','before']:self.assertIn('value="'+option+'" selected',page)
if __name__=='__main__':unittest.main()
