# Richtkoppler-Vergleich – HamLab

Referenzstand: Messreihen vom 29./30. September 2026. Generator FY6900, Messkanäle AD8307 A0/A1.

## Rücklaufunterdrückung bei 50 Ω

Alle Werte in dB. Berechnung: D_eff = (Rücklauf − Vorlauf)_Open − (Rücklauf − Vorlauf)_50Ω. Größere Werte bedeuten bessere Unterdrückung im gemessenen Aufbau.

| Frequenz MHz | Mini-Circuits ZFDC-20-3 | Eigenbau repariert | Eigenbau umgebaut | Eigenbau mit Deckel / besserem Short |
|---:|---:|---:|---:|---:|
| 1 | 42.83 | 25.21 | 25.48 | 26.11 |
| 7 | 42.20 | 25.47 | 25.92 | 26.57 |
| 14 | 40.01 | 22.25 | 26.42 | 28.10 |
| 21 | 37.75 | 19.74 | 26.24 | 30.18 |
| 28 | 35.78 | 17.96 | 25.16 | 31.10 |
| 30 | 35.40 | 17.57 | 24.88 | 30.71 |

| Messaufbau | Minimum 1–30 MHz | Maximum 1–30 MHz | Vorlauf | Rücklauf |
|---|---:|---:|---|---|
| Mini-Circuits | 35.40 dB | 42.95 dB | A0 | A1 |
| Eigenbau repariert | 17.57 dB | 26.70 dB | A0 | A1 |
| Eigenbau umgebaut | 24.69 dB | 26.65 dB | A1 | A0 |
| Eigenbau mit Deckel | 26.03 dB | 31.23 dB | A1 | A0 |

Die Werte sind eine effektive Richtschärfe des gesamten Aufbaus. Sie enthalten Abschlussfehler, Kanalabgleich, Leitungen und Kopplerleckage. Sie sind keine isolierte Hersteller-Spezifikation des Kopplers. Open-Normierung korrigiert den Amplitudenabgleich, keine phasenabhängige Leckage.

## Widerstandsprüfung des aktuellen Eigenbaus

Open-Normierung mit umbau1, A1 Vorlauf / A0 Rücklauf. Widerstände nach Gleichstrommessung: 25,2 Ω und 98,7 Ω. Soll-SWR gilt für rein reelle Widerstände an 50 Ω; deren HF-Verhalten ist nicht separat bestimmt.

| MHz | 25,2 Ω gemessen | Soll 1,984 | 98,7 Ω gemessen | Soll 1,974 |
|---:|---:|---:|---:|---:|
| 1 | 1.845 | 1.984 | 2.234 | 1.974 |
| 7 | 1.843 | 1.984 | 2.230 | 1.974 |
| 14 | 1.873 | 1.984 | 2.201 | 1.974 |
| 21 | 1.918 | 1.984 | 2.163 | 1.974 |
| 28 | 1.987 | 1.984 | 2.121 | 1.974 |
| 30 | 1.997 | 1.984 | 2.121 | 1.974 |

## Einordnung

Der Eigenbau erreicht nach mechanischem Umbau und geschlossenem Deckel etwa 26–31 dB effektive Richtschärfe. Die Mini-Circuits-Anordnung erreicht in diesen Messungen höhere Unterdrückung. Der Eigenbau eignet sich für die Suche nach SWR-Minima und zum Abstimmen. Die Widerstandsprüfung zeigt verbleibende Abweichungen bei absoluten SWR-Werten; eine universelle Genauigkeitsangabe lässt sich daraus nicht ableiten.

Koppeldämpfung und Richtschärfe sind verschiedene Größen. Diese Tabelle bestimmt keine absolute Koppeldämpfung und keinen zulässigen Watt-Messbereich. Dafür fehlt ein unabhängig gemessener Hauptleitungspegel je Frequenz.

## Quellen

- Mini-Circuits: zfdc_a0_vor_offen.csv; zfdc_a0_vor_50ohm.csv
- Eigenbau repariert: selbstbau_offen_1-30mhz_repair.csv; selbstbau_50ohm_1-30mhz_repair.csv
- Eigenbau umgebaut: selbstbau_offen_1-30mhz_umbau.csv; selbstbau_50ohm_1-30mhz_umbau.csv
- Eigenbau mit Deckel: selbstbau_offen_1-30mhz_umbau1.csv; selbstbau_50ohm_1-30mhz_umbau1.csv
- Widerstandsprüfung: selbstbau_25ohm_1-30mhz_umbau1.csv; selbstbau_100ohm_1-30mhz_umbau1.csv

Die ursprüngliche Messung mit defektem Schalter ist bewusst nicht als gültige Kopplerreferenz verwendet.
