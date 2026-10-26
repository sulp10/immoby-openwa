"""Property topic identification is separate from reservation authorisation."""
import json,re,unicodedata
from core.controller import EXCLUDED

def normalized(value):
 value=unicodedata.normalize('NFKD',str(value)).casefold()
 return re.sub(r'[^\w]+',' ',''.join(x for x in value if not unicodedata.combining(x))).strip()

def city_key(value):
 value=normalized(value)
 return 'roma' if value in {'roma','rome','rom','rome rm'} else value

def street_keys(street):
 words=normalized(street).split()
 stop={'via','viale','piazza','vicolo','lungotevere','lungomare','largo','dei','degli','delle','del','della','di','da','de','il','la','le','lo','gli','san'}
 core=[x for x in words if x not in stop]
 return {normalized(street),' '.join(core),core[-1] if core else ''}-{''}

def resolve_location(catalog,message,previous=None,*,expected=None):
 previous=previous or {};text=normalized(re.sub(r'(\d)\s*/\s*([A-Za-z])\b',r'\1\2',message))
 rows=[r for r in catalog if r['property_id'] not in EXCLUDED]
 aliases={r['property_id'] for r in rows for a in r.get('listing_aliases',[]) if (normalized(a['title']) and (' '+normalized(a['title'])+' ') in (' '+text+' ')) or (a.get('listing_id') and re.search(r'(?<!\d)'+re.escape(a['listing_id'])+r'(?!\d)',message) and ('airbnb' in text or 'booking' in text))}
 alias_candidates=sorted(aliases) if aliases else previous.get('alias_candidates',[])
 addresses=[(r['property_id'],a) for r in rows for a in r.get('identity_addresses',[])]
 road_word=bool(re.search(r'\b(via|viale|vicolo|piazza|lungotevere|lungomare|borgo|street|road|address|indirizzo)\b',text))
 hits=[];civic=None
 for pid,a in addresses:
  for key in sorted(street_keys(a['street']),key=len,reverse=True):
   match=re.search(r'(?<!\w)'+re.escape(key)+r'(?!\w)',text)
   if not match:continue
   number=re.match(r'\s*(\d{1,4}[a-z]?)(?!\w)',text[match.end():])
   if not (road_word or number or previous.get('status') in {'need_street','unrecognized_address'} and len(text.split())<=10):continue
   if number:civic=normalized(number[1]).replace(' ','')
   hits.append((pid,a));break
 cities={city_key(a['city']) for _,a in addresses}
 city=next((city_key(x) for x in cities|{'rome'} if (' '+x+' ') in (' '+text+' ')),None)
 if hits:
  streets={normalized(a['street']) for _,a in hits}
  if len(streets)>1:return {'status':'need_street','candidate_property_ids':[],'alias_candidates':sorted(aliases),'reason':'multiple_streets'}
  street=next(iter(streets))
 elif road_word:return {'status':'unrecognized_address','candidate_property_ids':[],'alias_candidates':alias_candidates}
 elif previous.get('street'):
  street=previous['street'];hits=[(pid,a) for pid,a in addresses if normalized(a['street'])==street]
  civic=previous.get('civic');city=city or previous.get('city')
  if previous.get('status')=='need_civic' and re.fullmatch(r'\d{1,4}\s*[a-z]?',text):civic=text.replace(' ','')
 else:return {'status':'need_street','candidate_property_ids':[],'alias_candidates':alias_candidates}
 if city:hits=[(p,a) for p,a in hits if city_key(a['city'])==city]
 if civic:hits=[(p,a) for p,a in hits if normalized(a.get('civic','')).replace(' ','')==civic]
 candidates={p for p,_ in hits}
 if alias_candidates:candidates&=set(alias_candidates)
 result={'street':street,'civic':civic,'city':city,'alias_candidates':alias_candidates,'candidate_property_ids':sorted(candidates),'authorizes_private_instructions':False}
 if not candidates:result['status']='mismatch' if expected else 'unrecognized_address'
 elif expected and expected not in candidates:result['status']='mismatch'
 elif len({city_key(a['city']) for p,a in hits if p in candidates})>1:result['status']='need_city'
 elif not civic and len({normalized(a.get('civic','')) for p,a in hits if p in candidates})>1:result['status']='need_civic'
 elif expected or len(candidates)==1:result['status']='confirmed'
 else:result['status']='need_listing'
 return result

def location_for(store,event,booking,catalog,now):
 # Scope resets for each verified reservation; unknown contacts expire after 24 hours.
 scope=event['sessionId']+':'+event['data']['from']+':'+(booking['reservation_id']+':'+booking['property_id']+':'+str(booking['support_from']) if booking else 'unverified')
 store.db.execute('CREATE TABLE IF NOT EXISTS location_checks(scope TEXT PRIMARY KEY,payload TEXT NOT NULL,updated REAL NOT NULL)')
 row=store.db.execute('SELECT payload FROM location_checks WHERE scope=? AND updated>?',(scope,now-86400)).fetchone()
 previous=json.loads(row[0]) if row else None
 expected=(booking.get('assigned_suite_id') if booking['property_id']=='3' else booking['property_id']) if booking else None
 result=resolve_location(catalog,event['data'].get('body',''),previous,expected=expected)
 with store.db:store.db.execute('INSERT OR REPLACE INTO location_checks VALUES (?,?,?)',(scope,json.dumps(result),now))
 return result

QUESTIONS={
 'need_street':'Ask only for the street address, house number and city of their accommodation. A listing title is not an alternative to the required street. Do not add diagnostic questions yet.',
 'need_civic':'The street is known but there are several house numbers. Ask for the exact house number.',
 'need_city':'Ask which city the accommodation is in.',
 'need_listing':'Several apartments or suites share this address. Ask for the exact Airbnb/Booking listing name or link, and the suite/room number if known.',
 'mismatch':'The reported location or listing does not match the verified booking. Briefly ask the guest to check the street, house number and exact listing name. Do not reveal the expected address or switch the booking.',
 'unrecognized_address':'The address does not match the current property directory. Ask the guest to check the street, house number, city and listing link. Do not guess.',
 'confirmed':'The property topic has been identified, but there is no verified reservation binding. Explain briefly that the booking must be verified before private entry instructions can be supplied. Do not request identity documents or payment details in chat.'}

STREET_QUESTIONS={
 'it':'In quale via si trova il tuo alloggio? Indicami anche il numero civico e la città.',
 'en':'What is the street address of your accommodation, including the house number and city?',
 'fr':'Quelle est l’adresse de votre logement, avec le numéro et la ville ?',
 'de':'Wie lautet die Straße Ihrer Unterkunft mit Hausnummer und Stadt?',
 'es':'¿Cuál es la dirección de tu alojamiento, con el número y la ciudad?',
 'pt':'Qual é a morada do alojamento, incluindo o número e a cidade?'
}
