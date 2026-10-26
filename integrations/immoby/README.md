# Immoby guest bot · OpenWA cloud integration

Leggere [la valutazione completa](VALUTAZIONE.md) per scelta del modello, costi, fine-tuning, Obsidian, disconnessioni e limiti attuali.

## Stato

Installazione locale su Mac in modalità bozze; successivo trasferimento su VPS. OpenWA, ricevitore, monitor e agente sono avviati. Nessuna risposta automatica agli ospiti è abilitata. GLM-5.3-Flash è stato verificato con una chiamata reale. Il dataset e le credenziali restano separati dal repository.

## Hosting temporaneo su Mac

`compose.local.yaml` mantiene console e ricevitore su `127.0.0.1` (porte 2785 e 18080). La conoscenza è in un volume privato di Docker, leggibile dal solo utente del contenitore; gli originali conservano i permessi precedenti. Creare prima il volume `immoby-guest-private-runtime` e copiarvi `knowledge/search.sqlite3` e `booking_bindings.json` con proprietario UID 10001 e permessi 0700/0600.

Avviare con `docker compose -f compose.yaml -f compose.local.yaml up -d --build`. L'installazione macOS usa una copia riservata in `~/Library/Application Support/Immoby Guest Bot`: i processi avviati da macOS possono così leggerla senza dipendere dalle autorizzazioni di accesso alla cartella Documenti. Un LaunchAgent esegue `start-local-host.sh` al login e riavvia i servizi se necessario. Il nome del progetto Compose va conservato nel file privato `.env` durante il trasferimento della copia locale, per riutilizzare gli stessi contenitori e volumi.

Il Mac deve restare acceso, connesso, collegato all'alimentazione e con la sessione utente aperta. Il processo impedisce la sospensione automatica quando è alimentato; non sostituisce un VPS e non garantisce il funzionamento con coperchio chiuso, logout o riavvio prima del login. Non avviare una seconda copia della stessa sessione WhatsApp sul futuro VPS.

La sessione `immoby-guest-bot`, una chiave operatore limitata alla sola sessione e il webhook firmato sono configurati. Restano necessari il collegamento dal telefono, un mittente email utilizzabile dal servizio e le associazioni attuali delle prenotazioni. La tolleranza di disconnessione è 300 secondi; revoca delle credenziali e richiesta di nuovo collegamento generano subito un avviso in coda. Un avviso in coda non è un'email consegnata.

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
