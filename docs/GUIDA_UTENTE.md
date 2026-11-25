# Vigilo — guida rapida

## Installazione

1. Copia la cartella `Vigilo` dove vuoi (es. `C:\Vigilo`).
2. Avvia `Vigilo.exe`. Per un collegamento sul Desktop: tasto destro sull'exe → *Mostra altre opzioni*
   → *Invia a* → *Desktop*. Se Windows mostra "PC protetto da Windows": *Ulteriori informazioni* →
   *Esegui comunque*.
3. Al primo avvio scegli la lingua (italiano o inglese). Si può cambiare poi nelle **Impostazioni**.
4. Il programma si apre una volta sola: se è già aperto, avviarlo di nuovo ne porta in primo piano
   la finestra (anche quando è nascosto nell'area di notifica).

## Aggiungere le telecamere

- Premi la **lente** (Cerca telecamere): trova da sola le telecamere e le porte aperte.
  **Aggiungi** sceglie in automatico il collegamento giusto.
- Oppure premi **+** e inserisci l'IP a mano.
- Tipi di collegamento:

  | Tipo | Quando |
  |---|---|
  | ICSee · RTSP | Porta 554 aperta — il più leggero |
  | ICSee · Nativo | Porta 34567 — il protocollo dell'app ICSee |
  | ICSee · Cloud | Telecamere di un'altra casa, col numero di serie (sperimentale, vedi il README) |
  | Altro RTSP | Qualsiasi telecamera con un indirizzo `rtsp://` |

- Utente: di solito `admin`. Password: quella dell'app ICSee (vuota se mai impostata).
- **Prova connessione** verifica tutto, cambia tipo se serve e riconosce da sola se la telecamera
  è motorizzata e se ha l'audio.

## Vista dal vivo

- **Griglia**: si adatta al numero di telecamere e alla finestra. **Evidenza**: la telecamera
  selezionata in grande, le altre intorno (clic su una telecamera per metterla in grande).
- **Doppio clic** su un video = ingrandisci in alta qualità; **Esc** = torna indietro.
- **F11** (o il pulsante con le frecce) = schermo intero con SOLO i video; Esc per uscire.
- Passando col mouse su un video compaiono i pulsanti: ingrandisci, foto, **ascolta**, registra.
- Bordo arancione e scritta **MOVIMENTO** = la telecamera ha visto un movimento.
- In alto: uso di CPU, RAM e disco (totale del PC e del solo programma).

## Audio dal vivo

- Premi l'**altoparlante** sul video, oppure **Ascolta** nella barra in alto, oppure tasto destro →
  *Ascolta*.
- Una telecamera alla volta; premi di nuovo (**Muto**) per smettere. Sul video compare la scritta
  verde **AUDIO**.
- Non si sente niente? La telecamera può non avere il microfono, o avere l'audio spento nelle sue
  impostazioni (app ICSee → impostazioni della telecamera → audio).

## Telecamere motorizzate

- Passa col mouse sul video: in basso a sinistra compare la croce. Tieni premuta una freccia per
  muovere, rilascia per fermare. Con la telecamera selezionata o ingrandita funzionano anche le
  frecce della tastiera.
- **Posizioni**: salva la posizione attuale con un nome (es. "Cancello") e richiamala con un clic.

## Rivedere le registrazioni (pulsante "Rivedi")

- Scegli la telecamera e il giorno nel calendario (i giorni registrati sono evidenziati).
- La barra in basso è la giornata: blu = registrato, arancione = movimento. Clicca un punto per
  vedere esattamente quel momento. Rotellina = ingrandisci la barra (oppure 24 h / 4 h / 1 h / 10 min).
- **Vai alle**: scrivi un orario (es. 14:30) e premi Invio.
- Velocità 1x … 16x. Spazio = play/pausa, frecce = 10 secondi.
- Elenco **Movimenti**: clicca un movimento per vederlo subito.
- Pulsante **altoparlante**: audio registrato (a velocità 1x).
- **Foto** salva l'immagine a piena risoluzione; **Esporta** salva una clip MP4 (30 s … 30 min) nella
  cartella `Exports`, pronta da mandare su WhatsApp o copiare su chiavetta.

## Registrazione e sovrascrittura (Impostazioni)

- Le registrazioni sono in `Video\Vigilo\<nome telecamera>\` (si può cambiare).
- **Modalità di registrazione**
  - *Continua*: registra sempre, in file da 5 / 10 / 15 / 30 minuti.
  - *Solo su movimento*: tiene solo quello che succede da qualche secondo prima di un movimento fino
    ai minuti scelti dopo l'ultimo movimento. I file durano 1 minuto. Sul video compare **ARMATA**
    mentre aspetta un movimento e **REC** quando sta tenendo la registrazione. Le telecamere col
    rilevamento movimento spento registrano sempre.
- **Registra anche l'audio**: salva anche l'audio, se la telecamera ha il microfono.
- **Sovrascrittura automatica**: quando si raggiunge un limite, le registrazioni più vecchie vengono
  cancellate per fare posto alle nuove: spazio massimo (GB), giorni da tenere, spazio libero minimo (GB).
- La registrazione avviene **solo mentre il programma è in funzione**. Chiudere la finestra non la
  ferma: Vigilo resta attivo nell'**area di notifica** (l'icona vicino all'orologio). Per chiuderlo
  davvero: tasto destro sull'icona → *Esci da Vigilo*. Si può cambiare in *Impostazioni → Avvio e
  funzionamento in background*.
- Mentre registra, Vigilo **tiene acceso il PC** (lo schermo può comunque spegnersi). La sospensione
  scelta da te (menu Start, tasto di accensione, chiusura del coperchio del portatile) avviene lo stesso.
- Attiva *Avvia il programma all'accensione del PC* così dopo un riavvio riprende a registrare.
- *Impostazioni → Prestazioni → Decodifica video sulla scheda grafica*: **Automatica** (predefinita)
  decodifica il video sulla scheda grafica e lascia più CPU libera, soprattutto nella vista
  ingrandita e nella riproduzione; sulla scheda della
  telecamera compare "· GPU". Scegli **Spenta** solo se l'immagine mostra problemi: allora fa tutto la
  CPU, come prima.
- Se Vigilo si interrompe per un errore viene **riavviato da solo** dopo qualche secondo e te lo
  segnala. Se continua a interrompersi smette di riprovare e ti avvisa; i dettagli sono in
  `%APPDATA%\Vigilo\vigilo.log`.

## File e cartelle

| Dove | Cosa |
|---|---|
| `%APPDATA%\Vigilo\config.json` | Impostazioni e telecamere (password comprese, in chiaro) |
| `<registrazioni>\<telecamera>\*.mkv` | Registrazioni |
| `<registrazioni>\<telecamera>\events\` | Movimenti (un file al giorno) |
| `<registrazioni>\<telecamera>\Snapshots\` | Foto |
| `<registrazioni>\Exports\` | Clip esportate |

Chi usava la versione precedente ("Telecamere Casa"): impostazioni e telecamere vengono importate
da sole al primo avvio e le registrazioni restano nella cartella di prima.

## Consigli di sicurezza

Queste telecamere hanno vulnerabilità note (per esempio chiunque sia sulla tua rete può leggerne la
password del Wi-Fi). Tienile su una rete separata (Wi-Fi ospiti o VLAN), non aprire mai le loro porte
sul router e dai a ogni telecamera una password diversa.
