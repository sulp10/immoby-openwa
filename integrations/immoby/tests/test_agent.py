import json,tempfile,unittest
from pathlib import Path
from cloud.openwa import Store
from cloud.agent import booking_for,process_one
class Tests(unittest.TestCase):
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
