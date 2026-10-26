"""Local controller for shadow testing. No guest messages are sent."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,re,sqlite3
from urllib.parse import urlencode
EXCLUDED={'40','30','29','34'}
ISSUES={'access','wifi','oven','toilet','hot_water','power','lift','water','other'}
SEVERITIES={'critical','urgent','routine','uncertain'}
@dataclass(frozen=True)
class BookingContext:
 reservation_id:str
 property_id:str
 verified_by_server:bool=False
 access_window_verified:bool=False
 assigned_suite_id:str|None=None

def check_context(ctx):
 if ctx.property_id in EXCLUDED:raise PermissionError('Property excluded')
 if not ctx.verified_by_server or not ctx.reservation_id:raise PermissionError('Reservation must be authenticated by the server, never by a guest assertion')

def retrieve(db,ctx,query,limit=5,source_kinds=('checkin','manual')):
 check_context(ctx)
 if not ctx.access_window_verified:raise PermissionError('Private guides require a verified delivery window')
 # Whole-building reservations require an explicitly verified suite assignment.
 pid=ctx.property_id
 if pid=='3':
  if ctx.assigned_suite_id not in {'4','5','6','7'}:raise PermissionError('Doria suite assignment required')
  pid=ctx.assigned_suite_id
 if not source_kinds or any(k not in {'checkin','manual'} for k in source_kinds):raise PermissionError('Unreviewed templates and historical answers are not authoritative retrieval')
 words=re.findall(r'\w+',query,flags=re.UNICODE)[:24]
 if not words:return []
 match=' OR '.join('"'+w+'"' for w in words)
 con=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True)
 try:
  rows=con.execute('SELECT d.payload FROM search s JOIN documents d ON d.doc_id=s.doc_id WHERE search MATCH ? AND d.property_id=? AND d.source_kind IN ('+','.join('?' for _ in source_kinds)+') ORDER BY bm25(search) LIMIT ?',[match,pid,*source_kinds,min(max(int(limit),1),10)]).fetchall()
 finally:con.close()
 return [json.loads(r[0]) for r in rows]

class AssistanceController:
 """Durable issue state and notification outbox. Not a language classifier.
 Inputs must come from a validated backend classifier, never guest-provided JSON.
 A failure counts only after a distinct assistance attempt was offered.
 """
 def __init__(self,path):
  self.con=sqlite3.connect(path)
  self.con.executescript('''CREATE TABLE IF NOT EXISTS issues (k TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, offered TEXT, tried TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'open'); CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY,result TEXT NOT NULL); CREATE TABLE IF NOT EXISTS outbox (notification_id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending');''')
 def handle(self,ctx,issue,event_id,*,severity='routine',action='clarify',step_id=None,incident_id='default'):
  check_context(ctx)
  if issue not in ISSUES or severity not in SEVERITIES:raise ValueError('Invalid classified issue/severity')
  if action not in {'clarify','offer_step','failed','resolved'}:raise ValueError('Invalid action')
  if not event_id or not incident_id:raise ValueError('Stable message event and incident IDs required')
  scope=f'{ctx.reservation_id}:{ctx.property_id}:{issue}:{incident_id}'
  eid=hashlib.sha256((scope+':'+event_id).encode()).hexdigest()
  with self.con:
   duplicate=self.con.execute('SELECT result FROM events WHERE event_id=?',(eid,)).fetchone()
   if duplicate:return json.loads(duplicate[0])
   self.con.execute('INSERT OR IGNORE INTO issues(k) VALUES (?)',(scope,))
   failures,offered,tried,status=self.con.execute('SELECT failures,offered,tried,status FROM issues WHERE k=?',(scope,)).fetchone();tried=json.loads(tried)
   route='assist';notice=None
   if severity in {'critical','urgent','uncertain'}:
    route={'critical':'emergency','urgent':'operator_priority','uncertain':'safety_clarification_and_operator'}[severity]
    # Unknown safety is not downgraded into routine troubleshooting.
    notice={'critical':'critical','urgent':'urgent','uncertain':'safety_uncertain'}[severity]
   elif status=='escalated':route='operator_followup'
   elif action=='resolved':status='resolved';offered=None;route='resolved'
   elif status=='resolved':raise ValueError('Open a new incident for a new occurrence')
   elif action=='offer_step':
    if not step_id or step_id in tried:raise ValueError('A fresh grounded step is required')
    if offered and offered!=step_id:raise ValueError('Resolve or clarify the current step first')
    offered=step_id
   elif action=='failed':
    if offered is None:raise ValueError('A failure requires a previous offered attempt')
    tried.append(offered);offered=None;failures+=1
    if failures>=3:status='escalated';route='operator_followup';notice='three_failed_attempts'
   if notice:
    nid=hashlib.sha256((scope+':'+notice).encode()).hexdigest()
    payload={'notification_id':nid,'reservation_id':ctx.reservation_id,'property_id':ctx.property_id,'issue':issue,'incident_id':incident_id,'priority':notice,'failed_attempts':failures,'tried_step_ids':tried,'recipients':['assigned_operator','owner_user'],'delivery_requires_configured_verified_recipients':True,'sent':False}
    self.con.execute('INSERT OR IGNORE INTO outbox(notification_id,payload) VALUES (?,?)',(nid,json.dumps(payload)))
    if severity=='critical':status='escalated'
   result={'route':route,'failed_attempts':failures,'current_step':offered,'tried_step_ids':tried,'status':status,'notification_queued':bool(notice),'guest_acknowledgement_required':bool(notice),'message_sent':False}
   self.con.execute('UPDATE issues SET failures=?,offered=?,tried=?,status=? WHERE k=?',(failures,offered,json.dumps(tried),status,scope));self.con.execute('INSERT INTO events VALUES (?,?)',(eid,json.dumps(result)))
  return result

def maps_search(address,city,kind,*,address_verified=False):
 if not address_verified:raise PermissionError('An unambiguous validated property address is required')
 if kind not in {'parking','luggage_storage'}:raise ValueError('Unsupported nearby service')
 term='parcheggio' if kind=='parking' else 'deposito bagagli'
 return 'https://www.google.com/maps/search/?'+urlencode({'api':'1','query':f'{term} vicino {address}, {city}'})

def general_playbook(issue):
 if issue not in ISSUES:raise ValueError('Unknown issue')
 path=Path(__file__).resolve().parents[1]/'prompts/general-playbooks.json'
 data=json.loads(path.read_text())
 return {'source_id':'general-playbook:'+issue,'scope':'global_operational_workflow','contains_property_facts_or_credentials':False,**data['playbooks'].get(issue,data['playbooks']['other'])}
