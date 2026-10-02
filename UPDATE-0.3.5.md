# HamLab 0.3.5 – Pegelabgleich und Leistung
Scope Average, 50 Ohm Sinus, 2026-10-01. Vorläufiger absoluter Abgleich.
Offsets A0/A1: 1 MHz -19.47/-19.60 dB; 7 MHz -19.39/-19.50;
30 MHz -18.35/-18.46. Linear in Hz interpoliert. Außerhalb werden
Endwerte verwendet, dort ist der Abgleich nicht bestätigt.
Steigungen und alter A1-Abgleich bleiben erhalten; neue Offsets wirken zusätzlich.
mw/vpp beziehen sich jetzt auf den AD8307-Eingang, nicht auf den Koppler-Hauptpfad.
SWR Open-Referenz wird um dieselbe Kanaldifferenz verschoben.
Alte SWR-Pegelschwellen werden identisch verschoben: bisherige SWR-Auswertung bleibt erhalten.
Alte und neue CSV-dBm nicht ohne entsprechende Umrechnung mischen.

Direkte Prüfung bei 7 MHz: hamlab power 7000000 0
Dann hamlab meter: etwa 632.5 mVpp an 50 Ohm sollten etwa 0 dBm / 1 mW ergeben.
0 dB ist nur für direkte Verbindung, kein Kopplerabgleich!

Hauptleitung über Koppler, A1 Vorlauf / A0 Rücklauf:
hamlab power 7000000 20
20 dB ist ein Beispiel, keine gemessene Koppeldämpfung des Eigenbaus.
Web/JSON zeigen forward_w und reverse_w. Beide verwenden denselben Faktor;
für genaue Rücklaufleistung muss dessen Koppeldämpfung separat geprüft werden.
Werte außerhalb -65..+10 dBm am jeweiligen Detektor erscheinen als null.
Diese Grenzen sind konservative Anzeigegrenzen, kein Nachweis von Messgenauigkeit.
hamlab power zeigt die aktuelle Leistung; hamlab power off deaktiviert Hauptleitungsanzeige.
Konfiguration nur RAM, nach Neustart aus.
Messfrequenz wird vom externen Generator nicht automatisch erkannt.
Aktives power hat Frequenzvorrang vor SWR; während DDS-Sweeps gilt DDS-Frequenz.
Die reale Wattbelastbarkeit des Kopplers/Abschlusses muss separat bekannt sein.

Build:
west build -b rpi_pico2/rp2350a/m33/w -S cdc-acm-console . -d build -p always && ./tools/flash_openocd.sh
