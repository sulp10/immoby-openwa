"""Recipient exclusions are enforced before classification and before transport."""
import os,re

def phone_number(value):
 if not isinstance(value,str):return None
 value=value.strip().lower()
 if '@' in value:
  value,host=value.rsplit('@',1)
  if host not in {'c.us','s.whatsapp.net'}:return None
  value=re.sub(r':\d+$','',value)
 value=re.sub(r'[\s()+.\-]','',value)
 if value.startswith('00'):value=value[2:]
 if len(value)==10 and value.startswith('3'):value='39'+value
 return value if re.fullmatch(r'[1-9]\d{6,14}',value) else None

def blocked_numbers():
 values=[x.strip() for x in os.getenv('BOT_BLOCKED_PHONES','').split(',') if x.strip()]
 normalized={phone_number(x) for x in values}
 if None in normalized:raise ValueError('Invalid blocked phone configuration')
 return normalized

def recipient_allowed(chat_id,resolved_phone=None):
 if not isinstance(chat_id,str):return False
 chat_id=chat_id.strip().lower()
 if chat_id.endswith('@lid'):
  # A privacy identifier is not a phone. Unknown mapping must fail closed.
  number=phone_number(resolved_phone)
 else:number=phone_number(chat_id)
 if not number or number in blocked_numbers():return False
 if resolved_phone is not None:
  alias=phone_number(resolved_phone)
  if not alias or alias in blocked_numbers():return False
 return True

def message_allowed(data):
 if not isinstance(data,dict) or data.get('fromMe') or data.get('isGroup'):return False
 if data.get('kind') in {'group','broadcast','status','newsletter','channel'}:return False
 for field in ['from','chatId','to']:
  value=str(data.get(field,'')).lower()
  if value.endswith(('@g.us','@broadcast','@newsletter')):return False
 return recipient_allowed(data.get('from'),data.get('senderPhone'))
