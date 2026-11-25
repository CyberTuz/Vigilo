"""
User-interface translations for Vigilo.

The source text in the code is English; tr() returns the Italian version when the
language is set to "it". To add a language, add a dictionary like IT below and an
entry to LANGUAGES.
"""

LANGUAGES = {"en": "English", "it": "Italiano"}
_lang = "en"


def set_language(lang):
    global _lang
    _lang = lang if lang in LANGUAGES else "en"


def get_language():
    return _lang


def tr(text):
    if _lang == "it":
        return IT.get(text, text)
    return text


IT = {
    # connection types
    "ICSee · Native": "ICSee · Nativo",
    "Other RTSP": "Altro RTSP",
    "Native": "Nativo",
    "Standard RTSP stream (port 554). The lightest connection.":
        "Stream RTSP standard (porta 554). È il collegamento più leggero.",
    "The ICSee app protocol (port 34567). Use it when port 554 is closed.":
        "Protocollo dell'app ICSee (porta 34567). Usalo quando la porta 554 è chiusa.",
    "Through the ICSee cloud with the serial number: works for cameras in another house too. "
    "Experimental: needs NetSdk.dll (see the README).":
        "Tramite il cloud ICSee col numero di serie: funziona anche per le telecamere di un'altra casa. "
        "Sperimentale: serve NetSdk.dll (vedi il README).",
    "Any camera with an rtsp:// address (Hikvision, Dahua, Reolink...).":
        "Qualsiasi telecamera con un indirizzo rtsp:// (Hikvision, Dahua, Reolink...).",
    "ICSee native": "ICSee nativo",
    # months / days
    "January": "Gennaio", "February": "Febbraio", "March": "Marzo", "April": "Aprile", "May": "Maggio",
    "June": "Giugno", "July": "Luglio", "August": "Agosto", "September": "Settembre", "October": "Ottobre",
    "November": "Novembre", "December": "Dicembre",
    "Monday": "Lunedì", "Tuesday": "Martedì", "Wednesday": "Mercoledì", "Thursday": "Giovedì",
    "Friday": "Venerdì", "Saturday": "Sabato", "Sunday": "Domenica",
    "MTWTFSS": "LMMGVSD",
    # camera (DVRIP) errors
    "Unknown camera error": "Errore sconosciuto della telecamera",
    "Unsupported version": "Versione non supportata",
    "Operation not allowed": "Operazione non permessa",
    "User already logged in": "Utente già collegato",
    "Wrong user name or password": "Utente o password errati",
    "Insufficient permissions": "Permessi insufficienti",
    "Wrong password": "Password errata",
    "User does not exist": "Utente inesistente",
    "User locked after too many attempts (try again in a few minutes)":
        "Utente bloccato per troppi tentativi (riprova tra qualche minuto)",
    "User locked": "Utente bloccato",
    "Access denied (code {code})": "Accesso rifiutato (codice {code})",
    "The camera refused the {stream} stream (code {code})": "La telecamera ha rifiutato lo stream {stream} (codice {code})",
    "Connection closed by the camera": "Connessione chiusa dalla telecamera",
    "Invalid reply: this does not look like an ICSee/XMeye camera":
        "Risposta non valida: non sembra una telecamera ICSee/XMeye",
    "Invalid packet from the camera": "Pacchetto non valido dalla telecamera",
    # cloud
    "The cloud connection needs NetSdk.dll (the Xiongmai SDK library).\n"
    "Put NetSdk.dll and StreamReader.dll in the \"sdk\" folder next to Vigilo.exe (see the README for details).":
        "Per il collegamento via cloud serve NetSdk.dll (la libreria SDK di Xiongmai).\n"
        "Metti NetSdk.dll e StreamReader.dll nella cartella \"sdk\" accanto a Vigilo.exe (dettagli nel README).",
    "Timed out": "Tempo scaduto",
    "Network error": "Errore di rete",
    "Cannot open the video (is the camera offline?)": "Impossibile aprire il video (telecamera non in linea?)",
    "Video connection failed (is the camera offline?)": "Collegamento video fallito (telecamera non in linea?)",
    "Too many simultaneous cloud viewers": "Troppe visioni contemporanee via cloud",
    "User does not exist (newer cameras may use a random user name or a token)":
        "Utente inesistente (le telecamere recenti possono usare un utente casuale o un token)",
    "User locked after too many attempts (try again later)": "Utente bloccato per troppi tentativi (riprova più tardi)",
    "Camera not found": "Telecamera non trovata",
    "Name resolution failed": "Risoluzione del nome non riuscita",
    "Camera offline (the cloud cannot find it)": "Telecamera non in linea (il cloud non la trova)",
    "Cloud server busy": "Server cloud occupato",
    "Cannot reach the cloud server": "Impossibile contattare il server cloud",
    "Connection failed": "Collegamento non riuscito",
    "Cloud server full": "Server cloud pieno",
    "Too many open connections": "Troppi collegamenti aperti",
    "This NetSdk.dll requires a developer account (see the README)":
        "Questa NetSdk.dll richiede un account sviluppatore (vedi il README)",
    "Connection failed (code {code})": "Collegamento non riuscito (codice {code})",
    "Cloud connection closed": "Collegamento cloud chiuso",
    "Cloud connection interrupted": "Collegamento cloud interrotto",
    "Invalid data from the cloud connection": "Dati non validi dal collegamento cloud",
    "Cloud connection error": "Errore del collegamento cloud",
    "NetSdk.dll not found (see the README)": "NetSdk.dll non trovata (vedi il README)",
    "NetSdk.dll not found.": "NetSdk.dll non trovata.",
    "The camera serial number is missing": "Manca il numero di serie della telecamera",
    "The cloud connection closed": "Il collegamento cloud si è chiuso",
    "The camera refused the video": "La telecamera ha rifiutato il video",
    "Enter the camera serial number": "Inserisci il numero di serie della telecamera",
    "the cloud allows the preview stream only": "il cloud permette solo lo stream di anteprima",
    "the cloud limits viewing to {n} min": "il cloud limita la visione a {n} min",
    "{codec} video via cloud": "Video {codec} via cloud",
    "Connected via cloud, but no video arrives": "Collegata via cloud, ma non arriva il video",
    "The cloud connection did not answer in time": "Il collegamento cloud non ha risposto in tempo",
    "Connecting via cloud...": "Collegamento via cloud...",
    "SDK library found:": "Libreria SDK trovata:",
    "Video goes through the ICSee cloud servers: it can take a few seconds.":
        "Il video passa dai server cloud ICSee: può metterci qualche secondo.",
    "Live audio is not available for cloud cameras": "L'audio dal vivo non è disponibile per le telecamere cloud",
    # messages from the cloud bridge process (xmcloud_bridge.py)
    "This NetSdk.dll needs the Microsoft Visual C++ 2005 Redistributable (x64)":
        "Questa NetSdk.dll richiede Microsoft Visual C++ 2005 Redistributable (x64)",
    "Cannot load NetSdk.dll": "Impossibile caricare NetSdk.dll",
    "Lost connection to the camera": "Collegamento con la telecamera perso",
    "SDK initialization failed": "Inizializzazione dell'SDK non riuscita",
    "Cannot receive the video": "Impossibile ricevere il video",
    "The video stopped arriving": "Il video non arriva più",
    "Internal error of the cloud connection": "Errore interno del collegamento cloud",
    # connection test
    "Port {port} is closed or the camera does not answer": "La porta {port} è chiusa o la telecamera non risponde",
    "{codec} video · {fps} fps": "Video {codec} · {fps} fps",
    "Connected, but no video arrives": "Collegata, ma non arriva il video",
    "The camera does not answer": "La telecamera non risponde",
    "Port {port} is closed (no RTSP)": "La porta {port} è chiusa (niente RTSP)",
    "Main": "Principale",
    "Preview": "Anteprima",
    "No video: check user name and password": "Nessun video: controlla utente e password",
    # live view states
    "Connecting...": "Connessione...",
    "Unreachable - retrying...": "Non raggiungibile - riprovo...",
    "Signal lost - retrying...": "Segnale perso - riprovo...",
    "retrying in 1 minute": "riprovo tra 1 minuto",
    "retrying...": "riprovo...",
    "Waiting for video...": "In attesa del video...",
    # archive / export / cleanup
    "There are no recordings at that time.": "In quel momento non ci sono registrazioni.",
    "Export error": "Errore di esportazione",
    "Overwrite: deleted {n} old recordings": "Sovrascrittura: eliminate {n} registrazioni vecchie",
    "Cannot set up automatic start:\n{err}": "Impossibile impostare l'avvio automatico:\n{err}",
    "The configuration cannot be read, a new one will be created.\n{err}":
        "Configurazione illeggibile, ne creo una nuova.\n{err}",
    # camera dialog
    "Camera": "Telecamera",
    "Camera {n}": "Telecamera {n}",
    "Edit camera": "Modifica telecamera",
    "New camera": "Nuova telecamera",
    "Connect a camera on your network (LAN) or in another house (cloud)":
        "Collega una telecamera di casa (rete locale) o di un'altra casa (cloud)",
    "Open ports found:": "Porte aperte trovate:",
    "Name": "Nome",
    "Connection type": "Tipo di collegamento",
    "IP address": "Indirizzo IP",
    "Port": "Porta",
    "User": "Utente",
    "Channel": "Canale",
    "Password (the one set in the ICSee app, empty if never set)":
        "Password (quella dell'app ICSee, vuota se mai impostata)",
    "Main URL (recording)": "URL principale (registrazione)",
    "Secondary URL (preview, optional)": "URL secondario (anteprima, facoltativo)",
    "Record this camera": "Registra questa telecamera",
    "Detect motion": "Rileva movimento",
    "Motorized (pan/tilt)": "Motorizzata (si può muovere)",
    "Test connection": "Prova connessione",
    "Save": "Salva",
    "Cancel": "Annulla",
    "Serial number (Cloud ID): in the ICSee app, camera settings > Device info":
        "Numero di serie (Cloud ID): nell'app ICSee, impostazioni della telecamera > Info dispositivo",
    "Port and channel must be numbers.": "Porta e canale devono essere numeri.",
    "Enter the camera serial number (Cloud ID).": "Inserisci il numero di serie (Cloud ID) della telecamera.",
    "Enter the IP address.": "Inserisci l'indirizzo IP.",
    "Enter the RTSP URL.": "Inserisci l'URL RTSP.",
    "Connecting through the ICSee cloud (it can take up to a minute)...":
        "Mi collego tramite il cloud ICSee (può volerci fino a un minuto)...",
    "Trying to connect...": "Provo a collegarmi...",
    "motorized": "motorizzata",
    "audio": "audio",
    "It works with \"{kind}\" (selected for you).": "Funziona con \"{kind}\" (l'ho selezionato io).",
    "It works!": "Funziona!",
    "Check the password (the one set in the ICSee app).": "Controlla la password (è quella impostata nell'app ICSee).",
    "Check the serial number and that the camera is online in the ICSee app.":
        "Controlla il numero di serie e che la telecamera risulti in linea nell'app ICSee.",
    "Check the IP address and that the camera is on.": "Controlla l'IP e che la telecamera sia accesa.",
    # settings
    "Settings": "Impostazioni",
    "Language, recording, overwrite, motion and startup": "Lingua, registrazione, sovrascrittura, movimento e avvio",
    "Language": "Lingua",
    "Program language": "Lingua del programma",
    "Recording": "Registrazione",
    "Recordings folder": "Cartella delle registrazioni",
    "Browse": "Sfoglia",
    "Recording mode": "Modalità di registrazione",
    "Continuous": "Continua",
    "Only on motion": "Solo su movimento",
    "Keep recording after the last motion for": "Continua a registrare dopo l'ultimo movimento per",
    "minutes": "minuti",
    "Recording starts a few seconds before the motion and continues for the minutes set above. "
    "In this mode files are 1 minute long. Cameras with motion detection turned off keep recording "
    "continuously.":
        "La registrazione parte qualche secondo prima del movimento e continua per i minuti indicati "
        "sopra. In questa modalità i file durano 1 minuto. Le telecamere col rilevamento movimento "
        "spento continuano a registrare sempre.",
    "Records all the time.": "Registra sempre.",
    "Length of each file": "Durata di ogni file",
    "Record audio too (when the camera has a microphone)": "Registra anche l'audio (se la telecamera ha il microfono)",
    "Automatic overwrite": "Sovrascrittura automatica",
    "When a limit is reached, the oldest recordings are deleted to make room\nfor new ones. Set 0 to disable a limit.":
        "Quando si raggiunge un limite, le registrazioni più vecchie vengono cancellate per\n"
        "fare posto alle nuove. Metti 0 per non usare quel limite.",
    "Maximum space for recordings": "Spazio massimo per le registrazioni",
    "Keep recordings for": "Tieni le registrazioni per",
    "days": "giorni",
    "Always leave free on the disk at least": "Lascia sempre libero sul disco almeno",
    "Motion detection": "Rilevamento movimento",
    "Sensitivity": "Sensibilità",
    "Low": "Bassa", "Medium": "Media", "High": "Alta",
    "Motion is marked in orange on the playback timeline.": "I movimenti vengono segnati in arancione nella riproduzione.",
    "Startup": "Avvio",
    "Start the program when the PC starts": "Avvia il programma all'accensione del PC",
    "Resume recording automatically at startup": "All'avvio riprendi a registrare automaticamente",
    "Each file will be about {size} per camera (measured on your recordings).":
        "Ogni file sarà di circa {size} per telecamera (misurato sulle tue registrazioni).",
    "With {n} camera(s) the maximum space is enough for about {days} days of continuous recording.":
        "Con {n} telecamera/e lo spazio massimo basta per circa {days} giorni di registrazione continua.",
    "{n} camera(s) use about {size} per day of continuous recording.":
        "{n} telecamera/e occupano circa {size} al giorno in registrazione continua.",
    "Shorter files = smaller files, easier to copy.": "File più corti = file più piccoli e più facili da copiare.",
    "Check the numbers you entered.": "Controlla i numeri inseriti.",
    "Restart the program now to change the language?": "Riavviare ora il programma per cambiare lingua?",
    # discovery
    "Find cameras": "Cerca telecamere",
    "Find the cameras connected to your network": "Trova le telecamere collegate alla rete di casa",
    "Network": "Rete",
    "Search": "Cerca",
    "Invalid network (e.g. 192.168.1.0/24)": "Rete non valida (es. 192.168.1.0/24)",
    "Searching...": "Ricerca in corso...",
    "{done}/{total} addresses": "{done}/{total} indirizzi",
    "None found": "Nessuna trovata",
    "1 camera found": "Trovata 1 telecamera",
    "{n} cameras found": "Trovate {n} telecamere",
    "No camera found.\nCheck that the PC is on the same network.":
        "Nessuna telecamera trovata.\nControlla che il PC sia sulla stessa rete.",
    "ICSee/XMeye with RTSP": "ICSee/XMeye con RTSP",
    "RTSP camera": "Telecamera RTSP",
    "ICSee/XMeye (native protocol only)": "ICSee/XMeye (solo protocollo nativo)",
    "Already added": "Già aggiunta",
    "Add": "Aggiungi",
    "Added": "Aggiunta",
    # playback
    "Playback": "Rivedi",
    "CAMERA": "TELECAMERA",
    "DAY": "GIORNO",
    "MOTION EVENTS": "MOVIMENTI",
    "Open folder": "Apri cartella",
    "Click the bar to jump to that time · mouse wheel to zoom":
        "Clic sulla barra per andare a quell'ora · rotellina per ingrandire",
    "Recorded": "Registrato",
    "Motion": "Movimento",
    "Play": "Play",
    "Pause": "Pausa",
    "Go to": "Vai alle",
    "Export": "Esporta",
    "Snapshot": "Foto",
    "No audio output device is available.": "Nessun dispositivo di uscita audio disponibile.",
    "Audio plays at 1x speed only": "L'audio si sente solo a velocità 1x",
    "No camera": "Nessuna telecamera",
    "No recordings on this day": "Nessuna registrazione in questo giorno",
    "No motion detected": "Nessun movimento rilevato",
    "Type a time, for example 14:30": "Scrivi un orario, per esempio 14:30",
    "Snapshot saved: {name}": "Foto salvata: {name}",
    "30 seconds from here": "30 secondi da qui",
    "1 minute from here": "1 minuto da qui",
    "5 minutes from here": "5 minuti da qui",
    "10 minutes from here": "10 minuti da qui",
    "30 minutes from here": "30 minuti da qui",
    "Exporting...": "Esportazione in corso...",
    "Clip exported": "Clip esportata",
    "Clip saved:\n{path}\n\nOpen the folder?": "Clip salvata:\n{path}\n\nAprire la cartella?",
    "Export failed.\n{err}": "Esportazione non riuscita.\n{err}",
    "Loading...": "Caricamento...",
    "End of recordings": "Fine delle registrazioni",
    "Paused": "In pausa",
    "Playing": "In riproduzione",
    # main window
    "DISK": "DISCO",
    "CAMERAS": "TELECAMERE",
    "No cameras.\nPress the magnifier to find them\nor + to add one.":
        "Nessuna telecamera.\nPremi la lente per cercarle\no + per aggiungerne una.",
    "Record all": "Registra tutte",
    "Stop all": "Ferma tutte",
    "Record": "Registra",
    "Stop REC": "Ferma REC",
    "Listen": "Ascolta",
    "Mute": "Muto",
    "Positions": "Posizioni",
    "Grid": "Griglia",
    "Focus": "Evidenza",
    "Ready": "Pronto",
    "No camera configured.\n\nDo you want to search for cameras on your network?":
        "Nessuna telecamera configurata.\n\nVuoi cercare le telecamere nella rete di casa?",
    "Listening: {name}": "In ascolto: {name}",
    "No audio from this camera (no microphone, or audio is off in its settings)":
        "Nessun audio da questa telecamera (niente microfono, o audio spento nelle sue impostazioni)",
    "Added: {name}": "Aggiunta: {name}",
    "Changed: {name}": "Modificata: {name}",
    "Delete the camera \"{name}\"?\n\nIts recordings stay on the disk.":
        "Eliminare la telecamera \"{name}\"?\n\nLe registrazioni già fatte restano sul disco.",
    "Recording stopped: {name}": "Registrazione fermata: {name}",
    "Recording started: {name}": "Registrazione avviata: {name}",
    "Recording started on all cameras": "Registrazione avviata su tutte le telecamere",
    "Stop recording on all cameras?": "Fermare la registrazione di tutte le telecamere?",
    "Recording stopped on all cameras": "Registrazione fermata su tutte le telecamere",
    "No picture available from this camera.": "Nessuna immagine disponibile da questa telecamera.",
    "Snapshot saved in {path}": "Foto salvata in {path}",
    "Snapshot saved": "Foto salvata",
    "Add a camera first.": "Aggiungi prima una telecamera.",
    "Settings saved": "Impostazioni salvate",
    "{cam}: going to \"{pos}\"": "{cam}: vado a \"{pos}\"",
    "Save the current position...": "Salva la posizione attuale...",
    "Delete a position": "Elimina una posizione",
    "Name of this position (e.g. Gate, Yard):": "Nome di questa posizione (es. Cancello, Cortile):",
    "Save position": "Salva posizione",
    "Position \"{name}\" saved": "Posizione \"{name}\" salvata",
    "Position \"{name}\" deleted": "Posizione \"{name}\" eliminata",
    "Back to the grid": "Torna alla griglia",
    "Enlarge": "Ingrandisci",
    "Exit full screen": "Esci da schermo intero",
    "Stop recording": "Ferma registrazione",
    "Start recording": "Avvia registrazione",
    "Stop listening": "Smetti di ascoltare",
    "Listen (live audio)": "Ascolta (audio dal vivo)",
    "Take snapshot": "Scatta foto",
    "Play recordings": "Rivedi le registrazioni",
    "Saved positions...": "Posizioni salvate...",
    "Open recordings folder": "Apri cartella registrazioni",
    "Edit...": "Modifica...",
    "Delete": "Elimina",
    "Full screen · press Esc to exit": "Schermo intero · premi Esc per uscire",
    "arrows or the pad on the video to move it": "frecce o croce sul video per muoverla",
    "High quality": "Alta qualità",
    "Esc to go back to the grid": "Esc per tornare alla griglia",
    "All cameras": "Tutte le telecamere",
    "1 camera": "1 telecamera",
    "{n} cameras": "{n} telecamere",
    "double-click a video to enlarge it": "doppio clic su un video per ingrandirlo",
    "Add the first camera with the + button\nor find it on the network with the magnifier":
        "Aggiungi la prima telecamera con il pulsante +\noppure cercala in rete con la lente",
    "ARMED": "ARMATA",
    "WAITING": "IN ATTESA",
    "AUDIO": "AUDIO",
    "MOTION": "MOVIMENTO",
    "{live}/{n} connected  ·  {rec} recording": "{live}/{n} collegate  ·  {rec} in registrazione",
    "program": "programma",
    "{size} free": "{size} liberi",
    "recordings {size}": "registrazioni {size}",
    "of {size}": "su {size}",
    "Closing the program stops the recording.\n\nClose anyway?":
        "Se chiudi il programma la registrazione si ferma.\n\nChiudere comunque?",
    "Closing, saving the recordings...": "Chiusura in corso, salvo le registrazioni...",
    "Vigilo is already open.": "Vigilo è già aperto.",
    # notification area, keep awake, watchdog
    "Startup and background": "Avvio e funzionamento in background",
    "Keep running in the notification area when the window is closed":
        "Resta attivo nell'area di notifica quando chiudi la finestra",
    "Keep the PC awake while recording (the screen can still turn off)":
        "Tieni acceso il PC mentre registra (lo schermo può comunque spegnersi)",
    "Show Vigilo": "Mostra Vigilo",
    "Quit Vigilo": "Esci da Vigilo",
    "Vigilo is still running in the notification area. Recording continues.":
        "Vigilo è ancora attivo nell'area di notifica. La registrazione continua.",
    "Vigilo was restarted after an error": "Vigilo è stato riavviato dopo un errore",
    # GPU decoding
    "Performance": "Prestazioni",
    "Video decoding on the graphics card (GPU)": "Decodifica video sulla scheda grafica (GPU)",
    "Automatic": "Automatica",
    "Off": "Spenta",
    "Checking the graphics card...": "Controllo della scheda grafica...",
    "Graphics card": "Scheda grafica",
    "Much less CPU for high-resolution video (enlarged view, playback, cameras without a secondary "
    "stream). When a stream does not decode on the GPU, the CPU takes over by itself.":
        "Molta meno CPU per il video ad alta risoluzione (vista ingrandita, riproduzione, telecamere "
        "senza stream secondario). Se uno stream non si decodifica sulla GPU, se ne occupa da sola la CPU.",
    "Now: {gpu} of {n} cameras decoded on the GPU.": "Ora: {gpu} telecamere su {n} decodificate sulla GPU.",
    "This PC cannot decode video on the graphics card: the CPU does it.":
        "Questo PC non può decodificare il video sulla scheda grafica: lo fa la CPU.",
    "Vigilo stopped working several times in a row and will not be restarted again.\n"
    "Details are in vigilo.log in {folder}.":
        "Vigilo si è interrotto più volte di seguito e non verrà riavviato di nuovo.\n"
        "I dettagli sono in vigilo.log nella cartella {folder}.",
}
