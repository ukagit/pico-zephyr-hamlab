# Live SWR 0.3.3
FY6900 -> Selbstbaukoppler -> Antenne. A1 vorwärts, A0 rückwärts.
Kalibrierung: umbau1 mit Deckel, Open und 50 Ohm, 1–30 MHz.
Die AD8307-Kalibrierung bleibt unverändert. Keine komplexe Fehlerkorrektur.

USB/Telnet: `hamlab swr 7100000` setzt die externe Messfrequenz und liest neu.
`hamlab swr` liest erneut, `hamlab swr off` deaktiviert.
Die externe Frequenz wird NICHT automatisch erkannt und NICHT am FY6900 gesetzt.
Nach jeder Generator-Frequenzänderung entsprechend nachführen.

API: POST /api/v1/config mit {"swr_frequency_hz":7100000}, 0 deaktiviert.
GET /api/v1/state enthält swr; GET /api/v1/measure liest beide Kanäle neu.
Web zeigt SWR, Frequenz und quality. Wert null bei unzuverlässiger Messung.
Open-Korrektur und 50-Ohm-Referenz werden linear in dB interpoliert.
3 dB Abstand zur Lastreferenz und Pegelschwellen sind heuristische Qualitätsregeln,
keine zertifizierte Fehlergrenze. Andere Koppler/Verdrahtungen brauchen neue Referenzen.
SWR-Konfiguration ist nach Neustart ausgeschaltet und wird nicht gespeichert.

Build:
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always
Nur nach erfolgreichem Build: ./tools/flash_openocd.sh
