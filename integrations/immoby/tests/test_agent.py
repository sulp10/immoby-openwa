import json,tempfile,unittest
from pathlib import Path
from cloud.openwa import Store
from cloud.agent import booking_for,process_one,validate_triage
class Tests(unittest.TestCase):
 def test_triage_rejects_non_string_retrieval_query(self):
  value={'issue':'access','severity':'routine','retrieval_query_it':['codice'],'search_kind':'none','failed_previous_step':False,'requested_human':False}
  with self.assertRaises(ValueError):validate_triage(value)
 def test_triage_rejects_unbounded_or_unrecognised_search(self):
  base={'issue':'access','severity':'routine','retrieval_query_it':'porta','search_kind':'arbitrary_url','failed_previous_step':False,'requested_human':False}
  with self.assertRaises(ValueError):validate_triage(base)
  with self.assertRaises(ValueError):validate_triage({**base,'search_kind':'none','retrieval_query_it':'x'*401})
 def test_followup_uses_only_the_current_verified_booking_issue(self):
  class Captured(Exception):pass
  class Fake:
   messages=None
   def complete(self,messages,**kwargs):self.messages=messages;raise Captured()
  for previous_reservation,expected in [('current','access'),('older',None)]:
   s=Store(':memory:');e=self.event();old={**e,'data':{**e['data'],'id':'previous'}};old_key,_=s.accept(old)
   with s.db:s.db.execute('INSERT INTO drafts VALUES (?,?,?)',(old_key,json.dumps({'reservation_id':previous_reservation,'triage':{'issue':'access'}}),90))
   b={'verified_by_pms':True,'reservation_id':'current','property_id':'8','status':'confirmed','support_from':0,'support_until':200}
   key,_=s.accept(e);client=Fake()
   with self.assertRaises(Captured):process_one(s,key,e,client,{'s:390000000000@c.us':b},Path('/not-used'),now=100)
   self.assertEqual(json.loads(client.messages[-1]['content'])['prior_issue'],expected);s.close()
 def event(self):return {'sessionId':'s','event':'message.received','idempotencyKey':'k','data':{'id':'m','from':'390000000000@c.us','body':'Help'}}
 def test_guest_cannot_assign_own_property(self):
  e=self.event();e['data']['property_id']='8';self.assertIsNone(booking_for(e,{},now=100))
 def test_cancelled_expired_and_excluded_booking_rejected(self):
  for b in [{'status':'cancelled','property_id':'8'},{'status':'confirmed','property_id':'40'},{'status':'confirmed','property_id':'8','support_until':50}]:
   base={'verified_by_pms':True,'reservation_id':'b','support_from':0,'support_until':200,**b};self.assertIsNone(booking_for(self.event(),{'s:390000000000@c.us':base},now=100))
 def test_critical_unknown_guest_alert_is_queued_before_second_call(self):
  class Fake:
   calls=0
   def complete(self,*a,**k):
    self.calls+=1
    if self.calls>1:raise AssertionError('No further model call required before alert')
    return {'content':json.dumps({'issue':'other','severity':'critical','retrieval_query_it':'','search_kind':'none','failed_previous_step':False,'requested_human':False})},{}
  s=Store(':memory:');event=self.event();key,_=s.accept(event);client=Fake();r=process_one(s,key,event,client,{},Path('/not-used'),now=100);self.assertFalse(r['automatic_send']);self.assertEqual(client.calls,1);self.assertEqual(s.db.execute('SELECT count(*) FROM notices').fetchone()[0],1);s.close()
if __name__=='__main__':unittest.main()
