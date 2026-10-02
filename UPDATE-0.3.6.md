# 0.3.6 Web-Leistungssteuerung
Live Leistung im Web: Messfrequenz 1–30 MHz, Koppeldämpfung 0–80 dB,
Vorlauf A0/A1 und Übernehmen/Ein, Aus. Direkte Prüfung: 0 dB, A0 wählen.
Automatische Anzeige in µW, mW, W. Detektorwerte bleiben auch ausgeschaltet sichtbar.
Eingaben werden erst mit Übernehmen wirksam. Aktive Werte stehen in der Ergebniszeile.
SWR-Kanalzuordnung bleibt unabhängig fest A1/A0. Kalibrierung unverändert gegenüber 0.3.5.
API POST /api/v1/power:
{"enabled":1,"frequency_hz":7000000,"coupling_millidb":0,"forward_channel":0}
Konfiguration nicht persistent. Beide Leistungsrichtungen verwenden denselben Kopplerfaktor.
CLI power verwendet die zuletzt gewählte Vorlaufrichtung, nach Neustart A1.
