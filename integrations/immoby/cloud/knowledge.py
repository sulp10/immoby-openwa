"""Curated property facts are selected by scope and issue, not keyword rank."""
import json,sqlite3
from pathlib import Path
from core.controller import check_context
ISSUE_TERMS={'access':'ingresso accesso portone chiavi','wifi':'wifi rete internet password router','toilet':'wc bagno scarico toilette corda pulsante','oven':'forno cucina comandi','hot_water':'acqua calda caldaia doccia','power':'corrente elettricita luce','lift':'ascensore','water':'acqua perdita','other':''}
def curated_facts(path,ctx,issue):
 check_context(ctx)
 if not ctx.access_window_verified:return []
 pid=ctx.property_id
 if pid=='3':
  if ctx.assigned_suite_id not in {'4','5','6','7'}:raise PermissionError('Doria suite assignment required')
  pid=ctx.assigned_suite_id
 with sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True) as c:
  rows=c.execute("SELECT payload FROM documents WHERE property_id=? AND source_kind='owner_fact' AND json_extract(payload,'$.authority')='owner_confirmed' AND COALESCE(json_extract(payload,'$.quarantined'),0)=0",(pid,)).fetchall()
 return [d for raw, in rows for d in [json.loads(raw)] if issue in d.get('issues',[])]
