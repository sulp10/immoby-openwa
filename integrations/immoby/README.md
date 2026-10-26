# Immoby guest bot · OpenWA cloud integration

Leggere [la valutazione completa](VALUTAZIONE.md) per scelta del modello, costi, fine-tuning, Obsidian, disconnessioni e limiti attuali.

## Stato

Installazione locale su Mac in modalità bozze; successivo trasferimento su VPS. OpenWA, ricevitore, monitor e agente sono avviati. Nessuna risposta automatica agli ospiti è abilitata. GLM-5.3-Flash è stato verificato con una chiamata reale. Il dataset e le credenziali restano separati dal repository.

## Hosting temporaneo su Mac

`compose.local.yaml` mantiene console e ricevitore su `127.0.0.1` (porte 2785 e 18080). La conoscenza è in un volume privato di Docker, leggibile dal solo utente del contenitore; gli originali conservano i permessi precedenti. Creare prima il volume `immoby-guest-private-runtime` e copiarvi `knowledge/search.sqlite3` e `booking_bindings.json` con proprietario UID 10001 e permessi 0700/0600.

Avviare con `docker compose -f compose.yaml -f compose.local.yaml up -d --build`. L'installazione macOS usa una copia riservata in `~/Library/Application Support/Immoby Guest Bot`: i processi avviati da macOS possono così leggerla senza dipendere dalle autorizzazioni di accesso alla cartella Documenti. Un LaunchAgent esegue `start-local-host.sh` al login e riavvia i servizi se necessario. Il nome del progetto Compose va conservato nel file privato `.env` durante il trasferimento della copia locale, per riutilizzare gli stessi contenitori e volumi.

Il Mac deve restare acceso, connesso, collegato all'alimentazione e con la sessione utente aperta. Il processo impedisce la sospensione automatica quando è alimentato; non sostituisce un VPS e non garantisce il funzionamento con coperchio chiuso, logout o riavvio prima del login. Non avviare una seconda copia della stessa sessione WhatsApp sul futuro VPS.

La sessione `immoby-guest-bot` è collegata dal telefono; la chiave operatore è limitata alla sola sessione e il webhook è firmato. Il mittente Aruba è configurato con SMTP su TLS implicito, porta 465. Il server ha accettato l'invio di prova; ciò non prova da solo la ricezione nella casella del destinatario. Restano necessarie le associazioni attuali delle prenotazioni. La tolleranza di disconnessione è 300 secondi; revoca delle credenziali e richiesta di nuovo collegamento generano subito un avviso in coda. Gli avvisi di disconnessione rimasti senza invio vengono chiusi dopo il ripristino stabile, evitando email che descrivono un guasto già risolto.

Il prompt usa risposte semplici, chiare e professionali nella lingua dell'ultimo messaggio significativo dell'ospite. Con messaggi senza una lingua riconoscibile mantiene la lingua precedente o quella verificata della prenotazione; altrimenti usa l'inglese. Codici, password, nomi, indirizzi e link restano invariati. La cronologia è isolata per prenotazione, appartamento e periodo di assistenza. Sono state provate risposte sintetiche in italiano, inglese, francese, tedesco, spagnolo e portoghese; nessun messaggio di prova è stato inviato agli ospiti.

`cloud.mail_setup` offre una configurazione Aruba utilizzabile solo su loopback: controlla Host, Origin e token contro richieste provenienti da altri siti, prova SMTP prima di salvare e scrive file 0600. Il campo opzionale `SMTP_PASSWORD_B64` evita che i caratteri speciali della password siano interpretati da Compose; base64 non cifra la password. Le credenziali restano segrete anche in questa forma. Il servizio di configurazione serve soltanto durante l'installazione e va arrestato dopo il completamento.

Durante la prima installazione lo spazio del disco virtuale Docker era stato esaurito dalla cache di compilazione. Sono stati liberati circa 6 GB di cache rigenerabile; database, sessione e volumi sono stati conservati. Il riavvio automatico avvia Compose una volta al login; le politiche di riavvio Docker gestiscono i processi, evitando avvii concorrenti durante gli aggiornamenti.

Le prove sintetiche del 26 ottobre comprendono 41 scenari: tutti i 16 scenari critici sono stati riconosciuti in entrambe le esecuzioni. La seconda esecuzione ha 38/41 classificazioni di gravità esatte; restano differenze su casi ambigui o non critici. Le prove non certificano risposte complete, interpretazione dei media o funzionamento con prenotazioni reali. Il dispatcher resta disabilitato.

## Componenti

- `cloud/openwa.py`: firma HMAC, contratto OpenWA verificato, deduplicazione, stato e coda degli avvisi.
- `cloud/service.py`: endpoint webhook, controllo periodico della sessione e invio email STARTTLS con ritentativi.
- `cloud/providers.py`: trasporti dei modelli e ricerca Brave per categorie locali dall’indirizzo verificato.
- `cloud/agent.py`: verifica del contesto della prenotazione, classificazione, RAG, stato di assistenza e bozze. Non invia risposte agli ospiti.
- `core/controller.py`: regole dei tentativi e ricerca separata per alloggio, riprese dal prototipo precedente.
- `compose.yaml`: servizi cloud riproducibili; OpenWA fissato al commit verificato, volumi persistenti e amministrazione non pubblica.

## Avvio previsto dopo il completamento degli accessi

1. VPS con Docker e spazio sufficiente. Copiare il progetto, creare `.env` dalla traccia e valorizzare le credenziali attraverso il gestore dei segreti. I file completati non vanno condivisi in chat o aggiunti a Git.
2. Copiare il dataset privato sul server con permessi limitati. `PRIVATE_DATA_DIR` deve contenere `knowledge/search.sqlite3`. Il contenitore del bot usa UID 10001: preparare una copia dedicata leggibile da quell’utente senza allargare i permessi degli originali.
3. Avviare inizialmente OpenWA, creare la sessione e collegarla dal telefono; poi registrare ID e webhook firmato. Gli esempi mostrano il formato del contratto, non contengono credenziali utilizzabili.
4. Collegare un mittente SMTP verificato e destinatari verificati. La coda non è una prova di consegna: fare un test autorizzato di ricezione e controllare gli errori.
5. Importare le associazioni attuali tra contatto WhatsApp e prenotazione da una fonte gestionale verificata. Non ricavarle dalle dichiarazioni dell’ospite o soltanto dal nome del contatto.
6. Avviare ricevitore, monitor e agente. Verificare disponibilità del modello, fonti, scenari di emergenza e sessione scollegata. Il sistema prepara soltanto bozze finché non viene completato e validato il dispatcher automatico.
7. Collegare un monitor esterno al VPS, backup protetti e procedure di ripristino. Non copiare la stessa sessione WhatsApp su due gateway attivi.

Eseguire i test locali con `python3 -m unittest discover -s tests -v`. La configurazione si verifica con `docker compose config --quiet` dopo aver fornito i valori obbligatori.

## Binding gestionale

Il futuro adattatore PMS scrive `booking_bindings.json`, indicizzato per `sessionId:chatId`. Ogni voce richiede `verified_by_pms: true`, `reservation_id`, `property_id`, `status` (`confirmed` o `checked_in`), `support_from`, `support_until`, `access_release_from`, `access_release_until` come timestamp Unix. Sono opzionali `assigned_suite_id`, `human_takeover`, `incident_id` e `verified_address` con indirizzo, città e verifica esplicita. Il file è privato e il bot non può modificarlo.

Restano da completare sincronizzazione PMS, dispatcher delle risposte, gestione degli incidenti successivi a una risoluzione, approvazione delle fonti, motore semantico, gestione completa degli allegati e console operatore. Questi elementi non vanno dedotti dalla presenza del solo gateway o del manifesto cloud.

## Esclusioni del destinatario e sandbox locale

`BOT_BLOCKED_PHONES` è una lista privata di numeri esclusi. Le esclusioni si applicano al ricevitore firmato, ai messaggi già in coda e al trasporto delle risposte. Tutti i gruppi, canali e broadcast vengono scartati prima di chiamare il modello. I contatti con identificativo `@lid` richiedono un numero risolto dal gateway; senza una corrispondenza verificabile vengono bloccati. Le conversazioni restano utilizzabili dagli operatori nella console OpenWA.

La sandbox è disponibile su **http://127.0.0.1:18082/** con `compose.local.yaml`. Scegliere immobile, eventuale suite Doria, tipo di mittente e fase del soggiorno; poi avviare una nuova prova e scrivere come un ospite. La risposta usa il modello configurato e la conoscenza filtrata per immobile. Il costo API della prova è reale; la prenotazione è simulata.

La sandbox non riceve credenziali WhatsApp o SMTP. Due controlli aggiuntivi impediscono le scritture verso OpenWA e l'invio di email in modalità sandbox. Stato, incidenti e conversazioni sono separati dal servizio operativo. Le richieste di intervento operatore vengono solo mostrate nella pagina. È accessibile soltanto da questo Mac e non da un telefono remoto.

Il catalogo contiene 26 tipologie di alloggio, esclusi i quattro immobili non più gestiti. La conoscenza aggiornata contiene 111 sorgenti HTML non vuote e 1.501 frammenti. Quattro guide precedentemente esportate vuote sono state recuperate dall'editor KrossBooking. APT. MONTI (45) non ha una guida assegnata; DORIA TOT (3) richiede la suite effettiva 4–7. Le fonti restano da validare per l'invio automatico: l'importazione non certifica che codici o contatti siano attuali.

Le prove comprendono il blocco del numero e dei gruppi anche attraverso il ricevitore HTTP firmato, senza aggiungere messaggi alla coda operativa, e risposte reali del modello a Wi-Fi, accesso e odore di gas. Non equivalgono a una validazione completa del servizio. L'associazione delle prenotazioni reali, il dispatcher e l'approvazione delle fonti restano da completare; nessuna risposta automatica agli ospiti è attiva.

## Identificazione dell'alloggio e controllo delle risposte

Il catalogo privato associa nomi pubblici e traduzioni di Airbnb/Booking alle tipologie del gestionale tramite via, civico e città. La rilevazione del 26 ottobre ha raccolto 34 annunci Airbnb e 17 Booking nell'account aperto; 38 annunci hanno una corrispondenza utilizzabile con 24 tipologie e 908 varianti di titolo. Gli immobili esclusi e le corrispondenze con civici discordanti restano fuori dalle associazioni automatiche. I dati effettivi sono nel volume privato e non nel repository.

Il bot chiede la via prima delle normali istruzioni specifiche, anche nella sandbox. Titolo, civico, città e suite servono a risolvere le ambiguità. La conferma viene ricordata per la conversazione/prenotazione, con scadenza dopo 24 ore di inattività; un indirizzo incompatibile blocca il recupero delle guide. Nome e indirizzo dichiarati identificano l'argomento, non autenticando la prenotazione: i codici richiedono ancora il binding PMS e la finestra di accesso. Le emergenze non attendono questa domanda.

Le informazioni confermate direttamente dal proprietario sono conservate separatamente come `owner_fact`, filtrate per immobile e problema e recuperate prima della ricerca per parole. Il ricostruttore locale del dataset conserva gli arricchimenti e le correzioni. La ricerca include anche termini operativi per ciascuna categoria del problema. La cronologia contiene le parole effettive dell'ospite, oltre alle bozze precedenti: una vecchia risposta del modello non prova che l'ospite abbia tentato un'azione.

Per le risposte ordinarie un secondo controllo confronta istruzioni, fatti e interpretazione con le fonti disponibili. Una risposta non sostenuta viene riscritta e controllata di nuovo; se non supera il controllo viene trattenuta e viene preparata assistenza umana. Le segnalazioni di fallimento vengono verificate rispetto allo specifico passaggio offerto prima di incrementare i tentativi. Le emergenze usano subito la policy di sicurezza, senza attendere questo controllo aggiuntivo. Questi controlli riducono il rischio di errori ma non costituiscono una garanzia di correttezza: il servizio resta in modalità bozze e richiede la validazione delle informazioni per l'uso operativo. I controlli aggiungono chiamate al modello e tempo di risposta.
