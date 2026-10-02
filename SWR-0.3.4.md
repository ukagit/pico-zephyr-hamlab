# Live SWR 0.3.4
FY6900 -> Selbstbaukoppler -> Antenne. A1 vorwärts, A0 rückwärts.
Web: http://192.168.178.69:8080, SWR ein / SWR aus.
Messung läuft im Hintergrund etwa alle 400 ms; Web aktualisiert alle 500 ms.
FY6900 von Hand verändern. Kein erneuter Messbefehl notwendig.
USB/Telnet: hamlab swr on, hamlab swr off.
Optional: hamlab swr 7100000 setzt die Korrekturfrequenz.
Standard beim Einschalten: 7.1 MHz, danach zuletzt gewählte Korrekturfrequenz.
Nach Neustart ausgeschaltet. Einstellungen nicht dauerhaft gespeichert.

Die FY6900-Frequenz wird nicht automatisch erkannt. Die Open-Korrektur bleibt
auf der gewählten Referenzfrequenz: geeignet zum manuellen Abstimmen im Umfeld
dieser Frequenz. Für breite Sweeps frequenzabhängige Auswertung mit Python nutzen.
Referenzen: Selbstbaukoppler umbau1 mit Deckel, 1–30 MHz.
Bei schwachem Signal oder Nähe zur Richtschärfegrenze erscheint kein Zahlenwert.
Die Qualitätsregeln sind heuristisch, keine garantierte Genauigkeitsangabe.

Build und Flash:
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always && ./tools/flash_openocd.sh
