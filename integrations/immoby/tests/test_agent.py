import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cloud.openwa import Store
from cloud.agent import booking_for,process_one,validate_triage,history_for,validate_sources
from core.controller import retrieve,BookingContext
class Tests(unittest.TestCase):
 def test_quarantined_guide_cannot_reach_model_context(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'knowledge.sqlite3';c=sqlite3.connect(path)
   c.executescript('CREATE TABLE documents(doc_id TEXT,property_id TEXT,source_kind TEXT,payload TEXT); CREATE VIRTUAL TABLE search USING fts5(doc_id UNINDEXED,text);')
   for doc_id,quarantined in [('bad',True),('good',False)]:
    c.execute('INSERT INTO documents VALUES (?,?,?,?)',(doc_id,'8','checkin',json.dumps({'doc_id':doc_id,'quarantined':quarantined})));c.execute('INSERT INTO search VALUES (?,?)',(doc_id,'portone'))
   c.commit();c.close()
   self.assertEqual([x['doc_id'] for x in retrieve(path,BookingContext('r','8',True,True),'portone')],['good'])
 def test_critical_safety_reply_does_not_retrieve_unverified_property_guide(self):
  class Fake:
   calls=0
   def complete(self,*args,**kwargs):
    self.calls+=1
    result={'issue':'other','severity':'critical','retrieval_query_it':'gas','search_kind':'none','failed_previous_step':False,'requested_human':False} if self.calls==1 else {'property_id':'8','source_doc_ids':['policy:safety'],'guest_reply':'Esci e chiama il 112 da fuori.','requires_operator':True,'action':'clarify'}
    return {'content':json.dumps(result)},{}
  with tempfile.TemporaryDirectory() as t,patch('cloud.agent.STATE',Path(t)),patch('cloud.agent.retrieve',side_effect=AssertionError('No guide for emergency')):
   store=Store(':memory:');e=self.event();key,_=store.accept(e)
   b={'verified_by_pms':True,'reservation_id':'current','property_id':'8','status':'confirmed','support_from':0,'support_until':200,'access_release_from':0,'access_release_until':200}
   r=process_one(store,key,e,Fake(),{'s:390000000000@c.us':b},Path('/unused'),now=100);self.assertEqual(r['controller']['route'],'emergency');store.close()
 def test_missing_access_instructions_force_handoff_without_three_fake_attempts(self):
  class Fake:
   calls=0
   def complete(self,*args,**kwargs):
    self.calls+=1
    result={'issue':'access','severity':'routine','retrieval_query_it':'portone','search_kind':'none','failed_previous_step':False,'requested_human':False} if self.calls==1 else {'property_id':'8','source_doc_ids':[],'guest_reply':'Mancano le istruzioni di ingresso.','requires_operator':False,'action':'clarify'}
    return {'content':json.dumps(result)},{}
  with tempfile.TemporaryDirectory() as t,patch('cloud.agent.STATE',Path(t)),patch('cloud.agent.retrieve',return_value=[]):
   store=Store(':memory:');e=self.event();key,_=store.accept(e)
   b={'verified_by_pms':True,'reservation_id':'current','property_id':'8','status':'confirmed','support_from':0,'support_until':200,'access_release_from':0,'access_release_until':200}
   r=process_one(store,key,e,Fake(),{'s:390000000000@c.us':b},Path('/unused'),now=100)
   self.assertEqual(r['controller']['route'],'operator');self.assertTrue(r['draft']['requires_operator']);self.assertEqual(store.db.execute('SELECT count(*) FROM notices').fetchone()[0],1);store.close()
 def test_general_sources_are_allowed_but_do_not_approve_property_facts(self):
  docs=[{'doc_id':'current','source_sha256':'hash'}]
  self.assertFalse(validate_sources(['general-playbook:access'],docs,'access',{'current':'hash'}))
  self.assertFalse(validate_sources(['policy:safety'],[], 'other'))
  self.assertTrue(validate_sources(['current','general-playbook:access'],docs,'access',{'current':'hash'}))
  for ids in [['other-property'],['general-playbook:wifi'],[{}],'current']:
   with self.assertRaises(PermissionError):validate_sources(ids,docs,'access')
 def test_history_cannot_cross_booking_or_property_or_support_window(self):
  s=Store(':memory:');e=self.event()
  for n,(reservation,property_id,created) in enumerate([('old','8',80),('current','9',80),('current','8',5),('current','8',80),('current','8',110)]):
   previous={**e,'data':{**e['data'],'id':str(n)}};k,_=s.accept(previous)
   with s.db:s.db.execute('INSERT INTO drafts VALUES (?,?,?)',(k,json.dumps({'reservation_id':reservation,'draft':{'property_id':property_id,'guest_reply':str(n)}}),created))
  history=history_for(s,e,{'reservation_id':'current','property_id':'8','support_from':10},now=100)
  self.assertEqual([h['draft']['guest_reply'] for h in history],['3']);s.close()
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
   with s.db:s.db.execute('INSERT INTO drafts VALUES (?,?,?)',(old_key,json.dumps({'reservation_id':previous_reservation,'triage':{'issue':'access'},'draft':{'property_id':'8'}}),90))
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
