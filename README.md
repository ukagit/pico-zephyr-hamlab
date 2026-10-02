# Pico-Zephyr-HamLab
HF-Laborinstrument von Ulrich Kleineaschoff, DL2DBG, für Raspberry Pi Pico 2 W mit Zephyr.

**Abschlussstand 0.3.7.** Hardwarebedienung, Build/Flash und Webansichten wurden am Aufbau erprobt. Der absolute Pegelabgleich nutzt einen Siglent-Scope als Arbeitsreferenz, keine rückführbare HF-Kalibrierung.

## Funktionen
- AD9850 DDS 0–40 MHz mit 125-MHz-Referenz.
- PE4302 Dämpfung 0–30 dB, ganze dB.
- Zwei AD8307 über ADS1115: ADC-Spannung, dBm, mW und Sinus-Vpp an 50 Ω.
- USB-Shell, TCP-Konsole, WLAN, JSON-API, OLED und Encoder.
- Web-Vollansicht und kompakte Messanzeige, Aktualisierung alle 500 ms.
- Interner DDS-Filter-Sweep mit Baseline, CSV, Cursor und −3-dB-Grenzen.
- Live-SWR und Leistungsanzeige über Richtkoppler.
- PC-Werkzeuge für FY6900, Siglent und automatisierte Messreihen.

## Hardware
| Baugruppe | Pico-Anschluss | Bedeutung |
|---|---|---|
| AD9850 | GP18 / 19 / 20 / 21 | W_CLK / FQ_UD / DATA / RESET |
| PE4302 | GP10 / 11 / 12 | DATA / CLK / LE |
| ADS1115 0x48 | GP16 / GP17 | SDA / SCL |
| AD8307 | ADS1115 A0 / A1 | HF-Eingänge, 50-Ω-Abschluss |
| SSD1306 128×64 0x3c | GP16 / GP17 | Gemeinsamer Bus |
| Encoder | GP15 / GP14 / GP13 | CLK / DT / Taster gegen GND |
| ADS1115 A2 / A3 | Noch nicht verwendet | Geplante Schottky-Detektoren |

I²C ist als Open-Drain-GPIO emuliert. Pull-ups nach 3,3 V und gemeinsame Masse verwenden. GPIO/ADC-Eingänge innerhalb ihrer zulässigen Spannungen betreiben.

## Build und Flash
Getestet: Zephyr 4.4.99, west 1.5.0, SDK 1.0.1. Anwendung im Verzeichnis zephyrproject/apps/pico-zephyr-hamlab.

    west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always &&
    ./tools/flash_openocd.sh

Das Skript erwartet eine CMSIS-DAP-Probe und RP2350-fähiges OpenOCD. Lokale Pfade über OPENOCD_ROOT und ZEPHYR_ROOT anpassen. Das SDK-OpenOCD der verwendeten Installation enthielt keine target/rp2350.cfg.

Alternativ build/zephyr/zephyr.uf2 per BOOTSEL kopieren. Nach Update hamlab info prüfen: Version 0.3.7. Browser Strg+F5.

## Bedienung
    hamlab info
    hamlab status
    hamlab freq 7100000
    hamlab att 10
    hamlab meter
    hamlab swr on
    hamlab swr 7100000
    hamlab swr off
    hamlab power 7000000 19
    hamlab power
    hamlab power off

Frequenzen in Hz: 123 bedeutet 123 Hz. Encoder-Taster wechselt ATT und Frequenzschritte 1/10/100/1000/10000/100000/1000000 Hz. OLED zeigt Frequenz, A0/A1, ATT und Auswahl.

| Oberfläche | Adresse |
|---|---|
| Vollansicht | http://<pico-ip>:8080/ |
| Kompakt | http://<pico-ip>:8080/compact |
| TCP-Shell | telnet <pico-ip> 23 |

Kompakt: A0/A1 oben, Frequenz und ATT darunter. Setzen oder Enter übernimmt Eingaben; unbestätigte Eingaben bleiben bei Statusaktualisierung erhalten.

WLAN-Zugangsdaten über Zephyr Credentials speichern: wifi cred add -h zeigt die versionsabhängige Syntax. Diagnose: network_status, net iface, wifi_stored. Nur WLAN-Zugangsdaten werden dauerhaft gespeichert. HTTP/Telnet sind unverschlüsselt und für das vertrauenswürdige lokale Netz gedacht.

## Filtermessung
DDS/FY6900 → Splitter → A0/A1. Baseline ohne Filter aufnehmen; danach DUT nur im A0-Zweig, A1 bleibt Referenz. Gleiche Einstellungen und Verdrahtung verwenden.

Durchlasskurve = (A0−A1)_DUT − (A0−A1)_Baseline. Gemeinsame Generatoränderungen und erfasste Zweigunterschiede werden kompensiert. Keine Phasenmessung.

Interner Sweep: höchstens 256 Punkte, 0–1000 ms zusätzliche Wartezeit, 1–8 Messungen je Punkt. ADC 860 SPS während Sweep, 128 SPS normal. 0 ms bedeutet weiterhin Wandlungs- und Übertragungszeit. −3-dB-Grenzen beziehen sich auf das Maximum der vollständigen DUT-Kurve.

## SWR und Leistung
SWR: A1 Vorlauf, A0 Rücklauf. Referenz gilt für den vermessenen Eigenbaukoppler mit Deckel, umbau1, 1–30 MHz. Andere Koppler brauchen eigene Referenzen. Open-Normierung ist skalar, keine komplexe Leckagekorrektur und keine Impedanzmessung.

Die externe FY6900-Frequenz wird nicht automatisch erkannt. Korrekturfrequenz bei breiten Sweeps nachführen. Nähe zur Lastreferenz und niedriger Pegel können den SWR-Zahlenwert unterdrücken.

Leistung: Vorlauf A0/A1 im Web wählbar. Direkte Messung: 0 dB Kopplung. Hauptleitung: gemessene Koppeldämpfung inklusive Zusatzdämpfer einstellen. Derselbe Faktor gilt für beide Richtungen; beide Abgriffe separat prüfen.

CLI power verwendet den zuletzt gewählten Vorlaufkanal, nach Neustart A1. Aktive Power-Frequenz hat Vorrang vor SWR für den Detektorabgleich; interner Sweep nutzt DDS-Frequenz. Diese Einstellungen sind nicht persistent.

[Kalibrierung und Messgrenzen](docs/kalibrierung.md) · [Richtkopplervergleich](docs/richtkoppler-vergleich.md)

## API
| Methode | Pfad | Bedeutung |
|---|---|---|
| GET | /api/v1/info | Version / Kalibrierung |
| GET | /api/v1/state | Letzte Werte, SWR, Leistung |
| GET | /api/v1/measure | Neue A0/A1-Messung |
| POST | /api/v1/config | Ein Feld: frequency_hz, attenuation_db oder swr_frequency_hz |
| POST | /api/v1/power | Leistungsanzeige konfigurieren |
| GET | /api/v1/sweep/status | Sweep-Zustand |
| GET | /api/v1/sweep/results | Messreihen |
| POST | /api/v1/sweep/start | Sweep starten |
| POST | /api/v1/sweep/stop | Sweep stoppen |

Power-Direktmessung A0:
    {"enabled":1,"frequency_hz":7000000,"coupling_millidb":0,"forward_channel":0}

19000 millidb bedeutet 19 dB. enabled:0 deaktiviert.

Sweep:
    {"mode":"baseline","start_hz":1000000,"stop_hz":11000000,"step_hz":100000,"dwell_ms":0,"samples":1}

DUT mit mode dut und identischen Einstellungen. DDS/ATT während Sweep gesperrt.

mw bezieht sich auf den Detektoreingang, power.forward_w/reverse_w auf den Kopplerfaktor. tap_w ist aus Kompatibilität null. measurement_valid/error prüfen; null ist kein Nullwattwert.

## PC-Werkzeuge
Optionen jeweils mit --help:
| Datei in tools/ | Zweck |
|---|---|
| sweep_fy6900.py | FY-Sweep, CSV, Gnuplot |
| measure_filter.py | Splitter-Baseline / Filter |
| sweep_antenna.py | Eigenbau-SWR, externe Referenz-CSV nötig |
| measure_swr.py | Mini-Circuits-Auswertung, fest A0 vor / A1 rück |
| calibrate_scope_hamlab.py | Gemeinsame FY/Scope/HamLab-Messung |
| calibrate_scope_hamlab_range.py | Bereichsprüfung, FY-Stellwerte bis 4 V |
| calibrate_ad8307.py / analyze_ad8307.py | Dämpfungsreihe / Kennlinienanalyse |
| embed_web.py | Webdateien als C-Header einbetten |

Scope-Werkzeuge erwarten die sds-status-Textausgabe; --fy/--sds ändern lokale CLI-Pfade. Scope-Skalierung/Average manuell einstellen. Qualitätsflag plausible prüft Scope-Verhältnis/Frequenz, nicht Verkabelung oder absolute Genauigkeit. Eingänge physisch umstecken.

CSV vor 0.3.5 enthält einen anderen absoluten Pegelbezug. Alte/neue Baselines nicht unbesehen mischen. Externe Koppler-Referenzdateien sind nicht im Firmwarepaket enthalten.

## Projektabschluss
Laborinstrument 0.3.7 ist am Aufbau erprobt. Geplante eigenständige Erweiterung: Leistungskoppler mit HF-Schottky-Detektoren an A2/A3. Nicht implementiert; eigene Hardwareauslegung und Kalibrierung erforderlich.

[Versionsübersicht](CHANGELOG.md) · [Historische Notizen](docs/entwicklung-bis-0.3.2.md)
