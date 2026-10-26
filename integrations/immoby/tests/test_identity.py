import unittest
from cloud.identity import resolve_location
CATALOG=[
 {'property_id':'8','name':'TEST A','identity_addresses':[{'street':'Via Andrea Alfa','civic':'12','city':'Roma'}],'listing_aliases':[{'title':'Test Terrace Two Suites'}]},
 {'property_id':'4','name':'ROOM 1','identity_addresses':[{'street':'Via Bruno Beta','civic':'38','city':'Roma'}],'listing_aliases':[{'title':'Test Internal Bathroom Suite'}]},
 {'property_id':'5','name':'ROOM 2','identity_addresses':[{'street':'Via Bruno Beta','civic':'38','city':'Roma'}],'listing_aliases':[{'title':'Test External Bathroom Suite'}]},
 {'property_id':'31','name':'TEST G','identity_addresses':[{'street':'Vicolo delle Gamma','civic':'9','city':'Roma'}]},
 {'property_id':'39','name':'TEST G','identity_addresses':[{'street':'Vicolo delle Gamma','civic':'10','city':'Roma'}]},
 {'property_id':'40','name':'EXCLUDED','identity_addresses':[{'street':'Via Retired','civic':'50','city':'Roma'}]}]
class Tests(unittest.TestCase):
 def test_title_alone_never_replaces_required_street(self):
  r=resolve_location(CATALOG,'My apartment is Test Terrace Two Suites')
  self.assertEqual(r['status'],'need_street');self.assertEqual(r['alias_candidates'],['8'])
 def test_street_is_requested_then_remembered_for_this_conversation(self):
  first=resolve_location(CATALOG,'Il Wi-Fi non funziona',expected='8')
  second=resolve_location(CATALOG,'Via Alfa 12 a Roma',first,expected='8')
  self.assertEqual(second['status'],'confirmed');self.assertEqual(second['candidate_property_ids'],['8'])
  self.assertEqual(resolve_location(CATALOG,'Ancora non funziona',second,expected='8')['status'],'confirmed')
 def test_wrong_street_never_changes_verified_booking(self):
  r=resolve_location(CATALOG,'Via Bruno Beta 38 Roma',expected='8')
  self.assertEqual(r['status'],'mismatch');self.assertNotIn('8',r['candidate_property_ids'])
 def test_same_street_requires_civic_or_listing(self):
  first=resolve_location(CATALOG,'Vicolo delle Gamma Roma')
  self.assertEqual(first['status'],'need_civic')
  self.assertEqual(resolve_location(CATALOG,'10',first)['candidate_property_ids'],['39'])
 def test_shared_address_needs_suite_when_booking_is_unknown(self):
  first=resolve_location(CATALOG,'Via Bruno Beta 38, Rome')
  self.assertEqual(first['status'],'need_listing')
  second=resolve_location(CATALOG,'Test External Bathroom Suite',first)
  self.assertEqual(second['candidate_property_ids'],['5']);self.assertEqual(second['status'],'confirmed')
 def test_verified_suite_context_and_wrong_suite_alias(self):
  r=resolve_location(CATALOG,'Via Bruno Beta 38 Roma',expected='4');self.assertEqual(r['status'],'confirmed')
  self.assertEqual(resolve_location(CATALOG,'Test External Bathroom Suite',r,expected='4')['status'],'mismatch')
 def test_new_unknown_street_invalidates_an_old_confirmation(self):
  first=resolve_location(CATALOG,'Via Alfa 12 Roma',expected='8')
  self.assertEqual(resolve_location(CATALOG,'Via Sconosciuta 99 Roma',first,expected='8')['status'],'unrecognized_address')
 def test_excluded_property_and_unknown_civic_are_not_matched(self):
  self.assertEqual(resolve_location(CATALOG,'Via Retired 50 Roma')['status'],'unrecognized_address')
  self.assertEqual(resolve_location(CATALOG,'Via Retired 50 Roma')['candidate_property_ids'],[])
  self.assertEqual(resolve_location(CATALOG,'Via Alfa 99 Roma')['status'],'unrecognized_address')
if __name__=='__main__':unittest.main()

class RuntimeGateTests(unittest.TestCase):
 def test_missing_street_never_reaches_private_retrieval(self):
  import json
  from pathlib import Path
  from unittest.mock import patch
  from cloud.agent import process_one
  from cloud.openwa import Store
  class Fake:
   calls=0
   def complete(self,*a,**kw):
    self.calls+=1
    result=({'issue':'wifi','severity':'routine','retrieval_query_it':'wifi','search_kind':'none','failed_previous_step':False,'requested_human':False} if self.calls==1 else {'property_id':'8','language':'it','guest_reply':'In quale via si trova il tuo alloggio?','source_doc_ids':[],'requires_operator':False} if self.calls==2 else {'supported':True,'problems':[]})
    return {'content':json.dumps(result)},{}
  event={'sessionId':'s','event':'message.received','idempotencyKey':'id','data':{'id':'id','from':'390000000000@c.us','body':'Il Wi-Fi non funziona'}}
  binding={'verified_by_pms':True,'reservation_id':'r','property_id':'8','status':'confirmed','support_from':0,'support_until':200,'access_release_from':0,'access_release_until':200}
  store=Store(':memory:');key,_=store.accept(event)
  with patch('cloud.agent.retrieve',side_effect=AssertionError('Private retrieval must be gated')):
   r=process_one(store,key,event,Fake(),{'s:390000000000@c.us':binding},Path('/unused'),now=100,property_catalog=CATALOG)
  self.assertEqual(r['property_location_check']['status'],'need_street');self.assertEqual(r['status'],'awaiting_property_location');self.assertFalse(r['automatic_send']);store.close()
 def test_curated_wc_fact_is_scoped_to_property_and_issue(self):
  import json,sqlite3,tempfile
  from pathlib import Path
  from core.controller import BookingContext
  from cloud.knowledge import curated_facts
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'knowledge.sqlite3';c=sqlite3.connect(path);c.execute('CREATE TABLE documents(property_id TEXT,source_kind TEXT,payload TEXT)')
   c.execute('INSERT INTO documents VALUES (?,?,?)',('36','owner_fact',json.dumps({'doc_id':'owner:36:toilet','authority':'owner_confirmed','issues':['toilet'],'text':'Use the side cord; front button is broken.'})));c.commit();c.close()
   self.assertEqual(len(curated_facts(path,BookingContext('r','36',True,True),'toilet')),1)
   self.assertEqual(curated_facts(path,BookingContext('r','8',True,True),'toilet'),[])
   self.assertEqual(curated_facts(path,BookingContext('r','36',True,True),'wifi'),[])
