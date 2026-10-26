import unittest,os
from unittest.mock import patch
from cloud.policy import recipient_allowed,message_allowed
from cloud.openwa import OpenWA,Store
from cloud.agent import process_one
class Tests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'BOT_BLOCKED_PHONES':'390001234567'});self.env.start()
 def tearDown(self):self.env.stop()
 def test_blocked_number_formats(self):
  for phone in ['+39 000 1234567','00390001234567','390001234567@c.us','390001234567@s.whatsapp.net','390001234567:3@s.whatsapp.net']:
   self.assertFalse(recipient_allowed(phone),phone)
 def test_groups_channels_and_unresolved_lids_are_blocked(self):
  for phone in ['1203000@g.us','status@broadcast','123@newsletter','456@lid']:
   self.assertFalse(recipient_allowed(phone),phone)
  self.assertFalse(recipient_allowed('456@lid','390001234567'))
  self.assertTrue(recipient_allowed('456@lid','390009876543'))
 def test_group_metadata_cannot_be_disguised_as_direct(self):
  for data in [{'from':'390009876543@c.us','isGroup':True},{'from':'390009876543@c.us','kind':'group'},{'from':'390009876543@c.us','chatId':'123@g.us'}]:self.assertFalse(message_allowed(data))
 def test_outgoing_transport_is_never_called_for_blocked_targets(self):
  def no_transport(*a,**k):raise AssertionError('Network must not be used')
  api=OpenWA('http://openwa-api:2785','test','s',no_transport)
  for target in ['390001234567@c.us','123@g.us','456@lid']:
   with self.assertRaises(PermissionError):api.send_text(target,'test','id')
   with self.assertRaises(PermissionError):api.request('/messages/send-text',{'chatId':target,'text':'test'})
 def test_queued_blocked_messages_never_reach_the_model_or_alerts(self):
  class NoModel:
   def complete(self,*a,**k):raise AssertionError('Blocked sender must not reach model')
  s=Store(':memory:');e={'sessionId':'s','event':'message.received','idempotencyKey':'test','data':{'id':'m','from':'390001234567@c.us','body':'test'}};key,_=s.accept(e)
  result=process_one(s,key,e,NoModel(),{},None,now=100)
  self.assertFalse(result['automatic_send']);self.assertEqual(result['status'],'inhibited');self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],0);s.close()
if __name__=='__main__':unittest.main()
