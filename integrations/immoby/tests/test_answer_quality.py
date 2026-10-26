import json,unittest
from cloud.answer_quality import review_draft
class Fake:
 def __init__(self,results):self.results=iter(results)
 def complete(self,*a,**kw):return {'content':json.dumps(next(self.results))},{}
class Tests(unittest.TestCase):
 def test_unsupported_instruction_is_repaired_and_checked_again(self):
  draft={'guest_reply':'Premi il pulsante cromato.','property_id':'36','language':'it','requires_operator':False}
  repaired={**draft,'guest_reply':'Tira la corda laterale.'}
  client=Fake([{'supported':False,'problems':['The front button is broken.']},repaired,{'supported':True,'problems':[]}])
  result,meta=review_draft(client,[],{},draft)
  self.assertEqual(result['guest_reply'],'Tira la corda laterale.');self.assertEqual(meta['status'],'repaired')
 def test_twice_rejected_reply_is_withheld(self):
  draft={'guest_reply':'Prova con un secchio.','property_id':'36','language':'it','requires_operator':False}
  client=Fake([{'supported':False,'problems':['Unsupported']},draft,{'supported':False,'problems':['Still unsupported']}])
  result,meta=review_draft(client,[],{},draft)
  self.assertNotIn('secchio',result['guest_reply']);self.assertTrue(result['requires_operator']);self.assertEqual(meta['status'],'withheld')
if __name__=='__main__':unittest.main()

class FailureTests(unittest.TestCase):
 def test_a_broken_unused_button_is_not_automatically_a_failed_cord_attempt(self):
  from cloud.answer_quality import confirm_failure
  client=Fake([{'failed':False,'reason':'Only the unused front button is reported broken.'}])
  self.assertFalse(confirm_failure(client,'cord-step','Pull the side cord; the front button is broken.','The button does not work, there is a side cord.')['failed'])
