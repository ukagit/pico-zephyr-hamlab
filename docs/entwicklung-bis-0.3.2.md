# HamLab für Raspberry Pi Pico 2 W / Zephyr

Migration des Messgeräte-Kerns aus `hamlab/main.py` (MicroPython). Der Name **HamLab** bezeichnet das Gerät mit AD9850 DDS, PE4302 Dämpfungsglied und zwei AD8307 HF-Messkanälen über ADS1115. Eigenständiges Zephyr-Projekt; kein bestehendes Transceiver-Projekt wird verändert.

## Pinbelegung aus dem Python-Archiv

| Baugruppe | Pico GPIO | Zweck |
|---|---:|---|
| AD9850 | 18, 19, 20, 21 | W_CLK, FQ_UD, DATA, RESET |
| PE4302 (Python-Klasse `PE4301_ATT`) | 10, 11, 12 | DATA, CLK, LE |
| ADS1115, 0x48 | 16, 17 | SDA, SCL; gemeinsame Leitungen mit OLED |
| AD8307 | ADS1115 A0, A1 | Messkanäle 0 und 1 |
| OLED SSD1306 128×64, 0x3c | 16, 17 | SDA, SCL; gemeinsam mit ADS1115 |
| Encoder | 15, 14 | CLK, DT; interne Pull-ups |
| Encoder-Taster | 13 | Taster gegen GND; interner Pull-up |
| Tastatur | 2–5, 9/6/7/8 | Reihen, Spalten; derzeit noch nicht portiert |
| Buzzer | 22 | Noch nicht portiert |

**Hardwarehinweis:** I²C auf GP16/GP17 wird als Open-Drain GPIO mit Pull-up emuliert. Externe Pull-ups (typisch 4,7 kΩ) sind für zuverlässige Funktion sinnvoll. Die Pinbelegung GP16/GP17 wurde am Aufbau bestätigt. Vor dem Anschluss die Verdrahtung prüfen. DDS-Referenz: 125 MHz; Maximalfrequenz aus `main.py`: 40 MHz. Dämpfung wie Python-Code: 0–30 dB in ganzen dB. Der AD8307-Detektor muss für genaue absolute Leistungsangaben mit Referenzmessungen kalibriert werden.

## Build

In Deiner Zephyr-Umgebung (Zephyr 4.4.99, Board wie beim Transceiver):

```sh
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console /pfad/zu/pico-zephyr-hamlab -d build/pico-zephyr-hamlab -p always
west flash -d build/pico-zephyr-hamlab --runner openocd
```

Für Dein vorhandenes OpenOCD-Flash-Skript kann stattdessen dessen Aufruf mit dem Build-Verzeichnis verwendet werden. **Hier wurde kein Build oder Hardwaretest durchgeführt:** `west` und das Zephyr-SDK sind in dieser Arbeitsumgebung nicht installiert. Board-spezifische Kconfig-Abhängigkeiten sind daher beim ersten Build gegebenenfalls an Deine lokale Zephyr-Konfiguration anzupassen.

## Bedienung

USB-Shell und die Transceiver-basierte TCP-Konsole (Port 23, über Telnet-Client erreichbar) bieten dieselben Befehle:

```text
hamlab status
hamlab info
hamlab freq 7100000
hamlab att 10
hamlab meter
network_status
wifi_stored
wifi cred add <SSID> <Sicherheitsmodus> <Passwort>
```

Die Syntax für `wifi cred add` hängt von Deiner Zephyr-Version ab; `wifi cred add -h` zeigt die Optionen. Zugangsdaten werden über Zephyrs Settings/NVS auf dem Pico gespeichert. WLAN wird beim Start automatisch mit gespeicherten Zugangsdaten verbunden; mit `wifi_stored` kann der Verbindungsversuch neu angefordert werden. `network_status` und `net iface` zeigen den Zustand. Nach der DHCP-Zuweisung `http://<pico-ip>:8080/` öffnen. Die TCP-Konsole auf Port 23 ist unverschlüsselt: nur in Deinem vertrauenswürdigen lokalen Netz verwenden.

| Methode | Pfad | Bedeutung |
|---|---|---|
| GET | `/` | HTML-Oberfläche mit 2-s-Aktualisierung |
| GET | `/api/v1/info` | Firmware-Version, Board und Kalibrierstand |
| GET | `/api/v1/state` | letzter Gerätezustand und letzte Messwerte |
| GET | `/api/v1/measure` | A0/A1 neu messen und Zustand liefern; bei I²C-Fehler HTTP 503 |
| POST | `/api/v1/config` | `{"frequency_hz":7100000}` **oder** `{"attenuation_db":10}` |

Beispiel: `curl -X POST http://<pico-ip>:8080/api/v1/config -H 'Content-Type: application/json' -d '{"frequency_hz":7100000}'`. Die API liefert Messwerte als `dbm`, `mw`, `vpp` und ADC-Spannung; `measurement_valid` zeigt an, ob die jüngste Messung erfolgreich war. `tap_w` ist seit Version 0.2.5 `null`. Beide Kanäle nutzen ab Version 0.2.9 ihre getrennten FY6900-Kalibrierungen.

## Entwicklungsstand / nächste Schritte

Die Kernfunktionen sind als C-Erstport implementiert. Tastenfeld, Bode-Sweep und Einstellungen im Flash fehlen noch. Der HTTP-Server verarbeitet eine Verbindung nach der anderen, setzt ein 2-s-Leselimit und ist für ein kleines lokales Netz gedacht; der einfache POST-Parser unterstützt genau die dokumentierten Einzelwerte und ist kein allgemeiner JSON-Parser. Erst nach lokalem Build und Messung an der Hardware sollten die Ausgänge als verifiziert gelten.

## Version 0.2.1: WLAN und TCP-Konsole

Der funktionierende Transceiver-Ansatz ist integriert: Wi-Fi Credentials über Settings/NVS, automatische Verbindung mit `NET_REQUEST_WIFI_CONNECT_STORED`, eigener Port-23-TCP-Server mit Dummy-Shell statt Zephyr-Telnet-Backend. HTML/API bleiben auf Port 8080. Die zuvor nötigen Zephyr-4.4-Korrekturen für Kconfig, `zsock_*` und USB-Log-Level sind enthalten.

Beim Update eines bereits entpackten Projekts aus dem TAR nur die Projektdateien überschreiben; vorhandene `tools/` bleiben bestehen. Nach dem Überschreiben einmal mit Board und Snippet neu bauen:

```sh
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always
./tools/flash_openocd.sh
```

Der Build wurde hier mangels `west` und SDK nicht ausgeführt. Die Settings/NVS-Partition bei 0x003f0000 mit 64 KiB ist wie im funktionierenden `app.overlay` des Transceivers eingetragen.

## Version 0.2.2

ADS1115-I²C auf die bestätigten Leitungen GP16 (SDA) und GP17 (SCL) gelegt.

## Version 0.2.3

ADS1115-Leseschleife auf genau acht Bit korrigiert; zuvor konnte `hamlab meter` den Controller blockieren.

## Automatisierte AD8307-Kalibrierung (PC, Version 0.2.4)

Die Firmware-API nimmt derzeit `attenuation_db` als ganze Zahl **0 bis 30 dB** an. Der PE4302-Datenblattbereich beträgt 0 bis 31,5 dB in 0,5-dB-Schritten; 33,5 dB sind mit diesem Baustein allein nicht möglich. Der PC-Messlauf verwendet nur den implementierten Bereich und ändert keine Kalibrierkonstanten im Pico.

1. FY6900 bei 1 MHz auf konstanten Ausgangspegel einstellen. Pegel vor den Dämpfungsgliedern an 50 Ω bestimmen. Bei einem gemessenen sinusförmigen Vpp-Wert: `P_dBm = 10*log10(((Vpp/(2*sqrt(2)))**2/50)/0.001)`. Wenn der Pegel etwa +10 dBm beträgt, `--source-dbm 10` verwenden.
2. Verkabelung: FY6900 -> HamLab-PE4302 -> externer 50-Ω-Stufendämpfer -> AD8307 A0. A1 danach separat mit derselben Strecke messen. Die Reihenfolge der beiden Dämpfer ist für die nominale Summe austauschbar, nicht für die Messung von Einfügefehlern.
3. Auf dem Ubuntu-PC mit dem Pico im gleichen Netz starten:

```sh
python3 tools/calibrate_ad8307.py --host 192.168.178.XX \
  --source-dbm 10 --external 0,20,40,60 \
  --internal 30,25,20,15,10 --output ad8307_a0.csv
```

Das Skript wartet bei jeder externen Schalterstellung auf Enter, stellt dann die internen Dämpfungen ein und liest fünfmal pro Stufe die JSON-API. Während der A0-Reihe stehen A1-Werte ebenfalls in der CSV; diese gelten nur als Rausch-/Übersprechmessung. Für A1 den HF-Eingang umstecken und einen zweiten Lauf mit neuem CSV-Namen starten. Am Ende stellt das Skript die interne Dämpfung auf 30 dB. Eine vorhandene CSV wird nicht überschrieben.

```sh
python3 tools/analyze_ad8307.py ad8307_a0.csv --source-dbm 21.8213 --max-total-db 65
```

Die Fit-Ergebnisse sind zunächst eine Diagnose. Besonders bei sehr kleinen Pegeln und am oberen Ende die Residuen prüfen. Die alte +49-dB-Tap-Korrektur gehört nicht zu dieser direkten Eingangskalibrierung.

## Version 0.2.5: Kalibrierung A0

Referenz FY6900 bei 1 MHz: 7,8 Vpp sinusförmig **an 50 Ω** = +21,8213 dBm.
14 nutzbare Mittelwert-Punkte aus `ad8307_a0.csv` (Gesamtdämpfung höchstens 65 dB; stärkere Dämpfung wegen beginnender Bodenbegrenzung ausgeschlossen) liefern `A0 dbm = 39,1979021 * voltage_v - 63,4736278`. Fit-Residuen: RMS 0,209 dB, Maximum 0,359 dB relativ zu nominalen Dämpfungsstufen; systematische Fehler der Quelle und Dämpfungsglieder sind darin nicht enthalten.

A1 hat weiterhin die alte, nicht neu geprüfte Kalibriergerade `40*U-82,05`; `calibrated` kennzeichnet den Stand beider Kanäle. Das alte, auf einen 49-dB-Messabgriff bezogene Feld `tap_w` bleibt aus Kompatibilitätsgründen im JSON, ist aber `null`. Leistung `mw` und `vpp` sind aus `dbm` für 50 Ω abgeleitet. Die A0-Kurve gilt zunächst für 1 MHz und den dokumentierten Messaufbau.

Für die bereits erfasste CSV ohne `nominal_input_dbm` kann das Analyse-Skript den später gemessenen Referenzpegel über `--source-dbm` nachtragen, ohne die Rohdaten zu verändern.

## Version 0.2.6: Firmware eindeutig erkennen

`hamlab info` an USB und TCP sowie `GET /api/v1/info` liefern dieselbe Versionsnummer. Der TCP-Starttext liest sie aus derselben Konstante. Nach einem Update prüfen:

```sh
hamlab info
curl http://<pico-ip>:8080/api/v1/info
```

Erwartet wird `"version":"0.2.6"`. Wenn die alte JSON-Ausgabe noch `"tap_w":0.000000` statt `null` zeigt, läuft noch eine Firmware vor 0.2.5. Nach dem Entpacken im Projektverzeichnis neu bauen und **das frische Build-Verzeichnis** flashen:

```sh
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always
west flash -d build --runner openocd
```

Das mitgelieferte `tools/flash_openocd.sh` verwendet `build/zephyr/zephyr.hex` aus diesem Projekt.

## Version 0.2.7: Flash-Skript wieder enthalten

`tools/flash_openocd.sh` verwendet `build/zephyr/zephyr.hex` aus diesem Projekt. Das Zephyr-SDK-OpenOCD enthält hier keine `target/rp2350.cfg`. Das funktionierende Transceiver-Skript verwendet deshalb das RP2350-OpenOCD der Arduino-rp2040-Installation. Die Pfade lassen sich mit `OPENOCD_ROOT` und `ZEPHYR_ROOT` überschreiben.

## Version 0.2.8: OpenOCD-Flash

Das mitgelieferte Skript ist die auf diesem Rechner erfolgreich verwendete Fassung aus `pico-zephyr-transceiver-control`. Standardmäßig verwendet sie `/home/ulrich/.arduino15/packages/rp2040/tools/pqt-openocd/4.1.0-1aec55e`. Bei einer anderen Version deren Installationsordner setzen:

```sh
OPENOCD_ROOT=/pfad/zu/pqt-openocd ./tools/flash_openocd.sh
```

## Version 0.2.9: Kalibrierung A1

Bei gleicher FY6900-Referenz (+21,8213 dBm, 1 MHz, 7,8 Vpp an 50 Ω) wurden mit HF-Signal an A1 13 nutzbare Stufen aus `ad8307_a1.csv` bis 65 dB Gesamtdämpfung ausgewertet. Daraus folgt `A1 dbm = 39,7556151 * voltage_v - 63,1440988`; die RMS-Abweichung zu den nominalen Stufen beträgt 0,121 dB, die maximale 0,218 dB. Sehr kleine Pegel am Messboden sind nicht Teil des Fits. Der Lauf hatte bei externer Dämpfung 0 dB keinen Messpunkt mit interner Dämpfung 10 dB; 13 Stufen reichen für den Fit.

`hamlab info` und `/api/v1/info` melden nun `a0_calibrated:true` und `a1_calibrated:true`. Beide `channels` in `hamlab meter` tragen `calibrated:true`; `vpp` wird aus dem berechneten dBm-Pegel für 50 Ω bestimmt. Die Fit-Residuen erfassen keine systematischen Pegelfehler des Generators oder der Dämpfungsglieder. Die Kalibrierungen gelten zunächst für die gemessene Frequenz und den dokumentierten Aufbau.

## Version 0.2.10: Kanalabgleich A1

Bei direkter Einspeisung des FY6900 mit Einstellung 0,18 V und 1–60 MHz lag A1 im Mittel 0,2244 dB unter A0. Die Firmware addiert daher 0,2244 dB zum berechneten A1-Pegel, bevor `mw` und `vpp` berechnet werden. `voltage_v` bleibt der unveränderte ADC-Messwert. `hamlab info` und `/api/v1/info` zeigen den Abgleich als `a1_alignment_db`. Dieser relative Kanalabgleich korrigiert nicht den gemeinsamen Frequenzgang von FY6900, Verkabelung und AD8307.

`tools/characterize_ad8307.py` akzeptiert Firmware 0.2.9 und 0.2.10. Neue CSV-Dateien enthalten `firmware_version` und `a1_alignment_db`; `reported_dbm` ist bei A1 ab 0.2.10 bereits abgeglichen. Für eine Wiederholung einen neuen `--output`-Dateinamen verwenden.

## Version 0.2.11: OLED und Encoder

Das vorhandene SSD1306-OLED (128×64, Adresse 0x3c) teilt sich GP16/GP17 mit dem ADS1115. Die OLED-Zeilen zeigen oben im gelben Bereich die DDS-Frequenz und Schrittweite, darunter A0 und A1 in dBm und unten die Dämpfung. Eine invertierte Zeile kennzeichnet die aktive Einstellung. Bei fehlendem OLED bleiben USB, Telnet und API benutzbar.

Der Drehencoder nutzt GP15 (CLK) und GP14 (DT), der Taster GP13 gegen GND. Beim Start ist ATT ausgewählt; Drehen verändert ihn in 1-dB-Schritten. Jeder Tasterdruck schaltet weiter: `ATT → FREQ 1 Hz → 10 Hz → 100 Hz → 1 kHz → 10 kHz → 100 kHz → 1 MHz → ATT`. Im Frequenzmodus verstellt Drehen die DDS innerhalb 0–40 MHz. Frequenz und ATT bleiben mit Shell und API gemeinsam bedienbar; der Bildschirm liest dieselben Werte. Die Anzeige misst A0/A1 periodisch und zeigt bei Messfehlern `--` statt eines alten Pegels. OLED und Encoder auf dem konkreten Aufbau nach dem Flashen überprüfen.

## Version 0.2.12: Thread-Start korrigiert

Zephyrs `K_THREAD_DEFINE` erwartet für den letzten Parameter eine ganzzahlige Millisekundenangabe. Die beiden OLED/Encoder-Threads sind nun mit `SYS_FOREVER_MS` definiert und werden nach der GPIO/OLED-Initialisierung durch `k_thread_start()` gestartet. Das korrigiert den C-Fehler `invalid operands to binary > (have 'k_timeout_t' and 'int')` beim Build von 0.2.11.

## Version 0.2.13: Große HTTP-Anzeige

Im Browser `http://<pico-ip>:8080/` öffnen (bei der bisherigen Adresse `http://192.168.178.69:8080/`). Die Seite zeigt Frequenz, A0 und A1 in dBm sowie Dämpfung groß an und aktualisiert sich alle 1,5 Sekunden aus `/api/v1/state`. Sie benutzt die periodischen ADS1115-Messungen des Display-Threads; ein Browser-Abruf startet keine zusätzliche I²C-Messung. Frequenzschritte, Direkteingabe und ATT-Tasten schreiben über `/api/v1/config`; USB, Telnet und OLED bleiben synchron. Die rohe JSON-Ausgabe ist aufklappbar. Der Web-Inhalt liegt lesbar unter `web/hamlab.html` und als eingebettete C-Zeichenkette in `src/hamlab_web.h`. Nach Änderungen an der HTML-Datei `python3 tools/embed_web.py` ausführen und neu bauen. Der Encoder zählt jetzt bereits nach zwei gültigen Flanken; Drehrichtung und Zählrate bitte am Gerät prüfen.

## Version 0.3.0: Interner AD9850-Sweep

HF-Aufbau: AD9850-Ausgang → gegebenenfalls **physisch wirksames** Dämpfungsglied → 3-dB-Splitter → A0 und A1. Beide AD8307-Eingänge müssen 50 Ω sehen. Vor dem ersten Lauf Pegel am Aufbau prüfen; ein Software-ATT-Wert schützt einen direkt verdrahteten Detektor nicht. Die Firmware bricht einen Lauf ab, wenn einer der angezeigten Pegel +10 dBm überschreitet. Mit Filter wird nur der A0-Zweig verändert, A1 bleibt Referenz. Die Baseline misst beide Zweige ohne Filter. Die Browserkurve zeigt nach dem zweiten Lauf `(A0−A1) mit Filter − (A0−A1) ohne Filter` in dB; passive Durchlassdämpfung erscheint negativ.

Im Browser `http://<pico-ip>:8080/` im Abschnitt **AD9850 · Online-Frequenzsweep** Start, Stopp, Schrittweite (MHz), Wartezeit und Messungen pro Punkt einstellen; dann **Baseline messen**, Filter in A0 einsetzen und **Filter messen**. Fortschritt und Messkurve aktualisieren sich während des Laufs. Der Browser kann eine CSV mit beiden Kanälen und der normierten Durchlasskurve speichern. Der DDS wird am Ende auf seine vorherige Frequenz zurückgestellt. Maximal 256 Punkte, 1–40 MHz, 0–1000 ms zusätzliche Wartezeit, 1–8 Messungen je Punkt. Messreihen liegen im RAM und gehen bei Neustart verloren; CSV vor dem Ausschalten speichern.

USB/Telnet erlaubt denselben Start mit `hamlab sweep baseline` und danach `hamlab sweep dut`. `hamlab sweep status` meldet Fortschritt, `hamlab sweep stop` bricht ab. Optional: `hamlab sweep baseline 1000000 11000000 100000`; für DUT dieselben Frequenzparameter angeben. Während des Sweeps sind externe Frequenz- und ATT-Änderungen gesperrt, die OLED-Aktualisierung pausiert für kürzere Messzeiten. Die HTTP-Endpunkte sind `POST /api/v1/sweep/start`, `POST /api/v1/sweep/stop`, `GET /api/v1/sweep/status`, `GET /api/v1/sweep/results`. Beispiel:

```sh
curl -X POST http://192.168.178.69:8080/api/v1/sweep/start \
  -H 'Content-Type: application/json' \
  -d '{"mode":"baseline","start_hz":1000000,"stop_hz":11000000,"step_hz":100000,"dwell_ms":25,"samples":1}'
```

Der Web-Inhalt besteht aus `web/hamlab.html` und `web/sweep.js`; nach Änderungen `python3 tools/embed_web.py` ausführen und neu bauen. Die Leistung des AD9850 kann mit der Frequenz variieren; A1 als Referenz reduziert diesen Einfluss auf die relative Filterkurve, beseitigt aber keine Anpassungsfehler im Splitter oder in den 50-Ω-Abschlüssen.

## FY6900-Frequenztest 1–5 MHz

`tools/sweep_fy6900.py` steuert FY6900-Kanal 1 mit der Workbench-CLI, misst beide Splitter-Ausgänge über HamLabs HTTP-API und schreibt CSV und PNG-Plot. Standard: 1–5 MHz in 1-MHz-Schritten; `--volts 2.2`, Sinus, Offset 0 V, drei Messungen pro Stufe. Zuerst A0 und A1 an die beiden 50-Ω-Ausgänge des Splitters anschließen und die Generator-Einstellung am Aufbau prüfen. Standardmäßig setzt das Skript intern 20 dB Dämpfung. Die FY-Option `--volts` ist eine **Einstellung**, keine unabhängige Messung der Spannung am Splitter-Eingang.

```sh
python3 tools/sweep_fy6900.py --host 192.168.178.69 \
  --fy /home/ulrich/Dokumente/GitHub/workbench/cmd/fy \
  --start-mhz 1 --stop-mhz 10 --step-mhz 0.01 \
  --volts 2.2 --attenuation 20 --output fy6900_1-10mhz.csv
```

Das Beispiel umfasst 901 Messpunkte in Schritten von genau 10 kHz und dauert deshalb merklich länger. Das Plotten benötigt `gnuplot-qt` und erzeugt standardmäßig eine gleichnamige PNG-Datei. Eine zusätzliche `_summary.csv` enthält eine Zeile pro Frequenz und dient als einfache Plot-Grundlage. Einen Plot aus vorhandenen Messdaten ohne neuen Sweep erstellen:

```sh
python3 tools/sweep_fy6900.py --plot-only --output fy6900_1-10mhz.csv
```

Bei einem zweiten Lauf mit nur A0-Signal würde A1 im gemeinsamen Autoscale die A0-Kurve zusammendrücken. Für einen A0-Plot mit wählbarem Pegelbereich und interaktivem Maus-Cursor:

```sh
python3 tools/sweep_fy6900.py --plot-only --output fy6900_1-10mhz.csv \
  --channels a0 --ymin-dbm -5 --ymax-dbm 2 --interactive
```

`--channels` unterstützt `both`, `a0`, `a1`; ohne `--ymin-dbm` und `--ymax-dbm` bleibt Autoscale aktiv. Im Qt-Fenster zeigt die Maus die Frequenz und den Pegel an. Taste `r` schaltet das Lineal für die Differenz zwischen zwei Cursorpositionen ein, Taste `h` zeigt die Bedienung. Der interaktive Plot zeichnet die gewählten Kurven in **einem** Diagramm, damit Gnuplots Mausfunktionen verfügbar bleiben. Der PNG-Plot mit beiden Kanälen hat weiterhin ein zweites Diagramm für A1−A0.

### Direkter AD8307-Pegeltest ohne Splitter

Für einen Test des Detektor-Messbereichs den tatsächlichen HF-Signalweg prüfen: Die Software-Einstellung `--attenuation 20` schützt den AD8307 nur, wenn das interne Dämpfungsglied physisch zwischen FY und AD8307 liegt. Bei einer Direktverbindung ohne diesen Dämpfer zeigte A0 schon für FY `--volts 0.2` etwa +1 dBm; höhere FY-Stellwerte lagen teils oberhalb des nutzbaren AD8307-Bereichs. `tools/characterize_ad8307.py` variiert FY-`--volts` bei konstanter Frequenz und markiert in der CSV, welcher Eingang tatsächlich verbunden ist:

```sh
python3 tools/characterize_ad8307.py --host 192.168.178.69 --input a0 \
  --start-mhz 1 --stop-mhz 1 --voltages 0.05,0.1,0.15,0.2 \
  --attenuation 0 --output ad8307_direct_a0.csv
```

Danach das HF-Kabel auf A1 umstecken und denselben Befehl mit `--input a1` und `--output ad8307_direct_a1.csv` wiederholen. Ein erweitertes Raster über 1–60 MHz ist mit `--start-mhz 1 --stop-mhz 60 --step-mhz 1` möglich. Die FY-Volt-Einstellungen sind keine rückführbaren Pegel in dBm; das Skript charakterisiert zunächst die Anzeige und bricht standardmäßig nach einem Messwert über +10 dBm ab. Für einen Frequenzgang bei nominal 0 dBm einen **festen** FY-Stellwert auswählen, der bei 1 MHz am angeschlossenen Kanal etwa 0 dBm ergibt, und dann einen einzelnen Volt-Wert über die Frequenz messen. Den Pegel während des Sweeps nicht per AD8307 nachregeln, weil sonst dessen Frequenzabweichung verdeckt würde. Am Ende werden FY-Ausgang und interne Dämpfung nach Möglichkeit ausgeschaltet beziehungsweise auf 30 dB gesetzt.

`--plot-output` wählt einen anderen PNG-Namen; `--no-plot` schreibt nur CSV. Die CSV enthält `fy_frequency_hz` und getrennt `hamlab_dds_frequency_hz`: Die interne DDS-Frequenz des Pico wird bei diesem Test nicht verstellt. Zusätzlich werden Einzelwerte, Mittelwerte und A1−A0 in dB geschrieben. Eine bestehende Mess-CSV wird nicht überschrieben. Zum Abschluss oder bei Fehlern versucht das Skript, den FY-Ausgang auszuschalten und intern 30 dB einzustellen. Es setzt HamLab-Firmware 0.2.9 oder 0.2.10 mit `/api/v1/info` und `/api/v1/measure` voraus. Für eine absolute Frequenzgangmessung muss der tatsächliche FY-Ausgangspegel bei jeder Frequenz separat bekannt sein.

## Filter messen: A0 als DUT, A1 als Referenz

FY6900 an den Eingang des 3-dB-Splitters; beide Ausgänge über gleichartige 50-Ω-Kabel an HamLab A0 und A1. Für den Splitter-Abgleich **noch keinen Filter** einsetzen, beide Zweige mit 50 Ω abschließen. Der interne HamLab-Dämpfer ist bei direkter Verdrahtung nicht im HF-Pfad; der Wert 0 ist hier nur sein Status. Beginne mit FY `--volts 0.18` und prüfe die Pegel am Aufbau. Die Messung stoppt bei einem angezeigten Pegel über +10 dBm.

Für den aktuellen Scan sind 1–11 MHz in 0,1-MHz-Schritten, FY CH1 mit `--volts 0.18`, HamLab `192.168.178.69`, zwei Messungen pro Punkt und ATT-Status 0 voreingestellt. Damit genügt für den ersten Lauf:

```sh
python3 tools/measure_filter.py --mode baseline
```

Dann den Filter **nur im A0-Zweig** einsetzen und mit demselben Raster messen:

```sh
python3 tools/measure_filter.py --mode dut --interactive
```

Der Dateiname enthält Start, Stopp, Schrittweite, FY-Stellwert, FY-Kanal, ATT und Samplezahl. Der DUT-Lauf findet die passende Baseline automatisch und nummeriert mehrere Filterläufe (`_dut_001`, `_dut_002`, …). Weitere Parameter gelten für **beide** Aufrufe, zum Beispiel `--start-mhz 1 --stop-mhz 60 --step-mhz 1`; für beide Läufe dieselben Werte verwenden. Eine bestehende Baseline wird nicht überschrieben.

```sh
python3 tools/measure_filter.py --mode baseline --host 192.168.178.69 \
  --start-mhz 1 --stop-mhz 60 --step-mhz 1 --volts 0.18 \
  --output splitter_baseline.csv
```

Jetzt **nur im A0-Zweig** den Filter einsetzen: Splitter → Filter → A0. Der A1-Zweig bleibt als Referenz unverändert. Am Filterausgang und Referenzzweig auf 50-Ω-Abschluss achten. Danach mit identischen Einstellungen messen:

```sh
python3 tools/measure_filter.py --mode dut --host 192.168.178.69 \
  --baseline splitter_baseline.csv \
  --start-mhz 1 --stop-mhz 60 --step-mhz 1 --volts 0.18 \
  --output filter_dut.csv --interactive
```

Es entstehen `filter_dut.csv` (beide Rohpegel), `filter_dut_loss.csv` (Einfügedämpfung **und** Durchlasskurve) und `filter_dut_loss.png`. `--interactive` öffnet zusätzlich den Gnuplot-Cursor. Der Plot zeigt `transmission_db`, also eine nach unten gerichtete Filterkurve: −3 dB bedeuten 3 dB Dämpfung. Die CSV-Spalte `insertion_loss_db` gibt denselben Verlust positiv an. Es gilt `insertion_loss_db = (A0−A1) ohne Filter − (A0−A1) mit Filter` und `transmission_db = −insertion_loss_db`. Das gleicht den Splitterunterschied und die gemeinsame FY-Pegeländerung aus. Für spätere Auswertungen ohne Hardware:

```sh
python3 tools/measure_filter.py --mode analyze --baseline splitter_baseline.csv \
  --dut filter_dut.csv --output filter_neu_loss.csv --interactive
```

Das Werkzeug akzeptiert Firmware 0.2.9 bis 0.2.11 und protokolliert den A1-Kanalabgleich. Zwei Läufe müssen denselben A1-Kanalabgleich, FY-Stellwert und interne ATT-Einstellung haben. Baseline 0.2.10 kann damit für 0.2.11 weiterverwendet werden, sofern die Verdrahtung unverändert ist. CSV und Plot werden nicht überschrieben. Den Filter außerhalb des AD8307-Messbereichs nicht anhand der Kurve beurteilen.
Der DUT-Lauf darf nur einen Teilbereich der Baseline abdecken, zum Beispiel 1–11 MHz aus einer Referenzmessung über 1–60 MHz. Jeder DUT-Frequenzpunkt muss in der Baseline vorkommen. In der Shell muss `\` direkt vor dem Zeilenende stehen, ohne Leerzeichen dahinter.
Für einen DUT-Lauf mit `--step-mhz 0.1` genügt eine Baseline in 1-MHz-Schritten nicht. Zuerst die Baseline für den gewünschten Bereich mit 0,1-MHz-Schritten neu messen, dann denselben DUT-Bereich verwenden. Eine Interpolation der Splitter-Referenz erfolgt bewusst nicht.

## Version 0.3.1: schneller Sweep

Der ADS1115 misst während des internen Sweeps mit 860 SPS statt 128 SPS. Die zusätzliche Wartezeit darf 0 ms sein; die zwei nacheinander gemessenen Kanäle brauchen dennoch jeweils eine ADC-Wandlung und Software-I²C-Übertragung. Normale Einzelmessungen behalten 128 SPS. Bei kleinen Pegeln den schnellen Sweep mit längerer Wartezeit und mehreren Messungen vergleichen, da 860 SPS stärker rauschen kann.

## Version 0.3.2: −3-dB-Grenzen

Nach einer vollständigen DUT-Messung zeichnet die Webgrafik die −3-dB-Linie bezogen auf das Maximum der normierten Durchlasskurve. Die nächstliegenden Schnittpunkte links und rechts vom Maximum werden zwischen Messpunkten linear interpoliert. Anzeige: f₁, f₂ und Bandbreite; fehlt ein Schnittpunkt im gewählten Frequenzbereich, wird das angegeben. Die Marker werden nicht für eine unvollständige Messung berechnet.

## Skalares SWR mit zwei ZFDC-20-3 und FY6900

Verdrahtung: FY6900 → zwei entgegengesetzt orientierte Richtkoppler → Messport;
A0 misst vorwärts, A1 rückwärts. Offen-Referenz und 50-Ω-Messgrenze wurden mit
0,57 V FY-Einstellung (CH1), 0 dB HamLab-ATT, je zwei Samples und 1–30 MHz in
1-MHz-Schritten gemessen. Die Rohdateien sind externe Messdaten und gehören nicht
zum Firmware-Archiv. Mit unveränderter Verdrahtung und gleicher Generator-Einstellung:

```sh
python3 tools/measure_swr.py \
  --open zfdc_a0_vor_offen.csv --load zfdc_a0_vor_50ohm.csv \
  --dut mein_pruefling.csv --measure-dut --host <PICO-IP> \
  --output swr_mein_pruefling.csv
```

Das Tool ruft `sweep_fy6900.py` mit den Einstellungen und dem Raster der
Offen-Datei auf, misst den Prüfling und erstellt CSV sowie einen Gnuplot-PNG.
Ohne `--measure-dut` kann man eine vorhandene DUT-Datei auswerten; ohne `--dut`
nur die frequenzabhängige Messgrenze darstellen. `--no-plot` funktioniert ohne
Gnuplot. Die CSV enthält `dut_rl_db`, `dut_swr` und `limit_reached`. Für Werte
innerhalb 3 dB der 50-Ω-Messgrenze gibt es keinen numerischen SWR-Wert, weil
der Messaufbau gute Anpassungen dann nicht mehr sicher unterscheiden kann.
Die Berechnung verwendet `RL = (A1−A0)_offen − (A1−A0)_DUT` und
`SWR = (1+10^(−RL/20))/(1−10^(−RL/20))` für positive RL außerhalb der Grenze.
50 Ω ist eine beobachtete Messgrenze, keine skalare Vektorkorrektur des Kopplers.
Die FY6900-Kalibrierung gilt nicht automatisch für den AD9850-Generator.
