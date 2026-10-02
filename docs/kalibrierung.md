# Pegelabgleich und Messgrenzen
Stand 0.3.7, Messungen 1. Oktober 2026.

## Referenz und Firmware
FY6900 direkt an AD8307 mit 50 Ω, Siglent SDS1202X-E hochohmig parallel, Average und kurze Masseverbindung. Pico-WLAN-Einstrahlung erhöhte vorher Vpp. Zehn Sekunden Einschwingzeit im automatisierten Lauf.

Sinus: P_mW = 1000 × Vpp² / (8 × 50). 0 dBm = 1 mW = 223,6 mV RMS = 632,5 mVpp.
FY-Stellwerte sind keine gemessenen Referenzpegel.

Alter absoluter Bezug war etwa 19 dB zu hoch. Historischer Koppler-/Referenzversatz ist vermutet, nicht nachgewiesen. Der aktuelle Scope-Abgleich ist keine rückführbare Kalibrierung.

Steigungen bleiben:
- A0: 39.1979021169 × U − 63.4736278330.
- A1: 39.7556150827 × U − 63.1440988355 + 0.2244167.

Zusätzliche Offsets:
| Frequenz | A0 dB | A1 dB |
|---:|---:|---:|
| 1 MHz | −19,47 | −19,60 |
| 7 MHz | −19,39 | −19,50 |
| 30 MHz | −18,35 | −18,46 |

Linear in Hz interpoliert; außerhalb Endwerte gehalten, dort nicht bestätigt. Alte A1-Ausrichtung ist in den zusätzlichen Offsets berücksichtigt. Gemeinsame Frequenzabhängigkeit von Scope und HF-Messpfad nicht getrennt bestimmt.

SWR-Open-Referenz wird um dieselbe Änderung der Kanaldifferenz verschoben. Relative Pegelschwellen ebenfalls verschoben; vorhandener RL/SWR-Abgleich bleibt erhalten.

## Bereichsprüfung 1 MHz
Direkt, etwa −18,4 bis +9,8 dBm, gemittelte Restkorrekturen:
- A0: etwa −0,20 bis +0,64 dB.
- A1: etwa −0,29 bis +0,11 dB.
Oberer A0-Unterschied noch nicht eindeutig Detektor/Scope zugeordnet.

A1-Handdämpferprüfung, nominale Dämpfung bei 0-dBm-Referenz:
| Soll dBm | Gemessen dBm | Abweichung dB |
|---:|---:|---:|
| −20 | −19,81 | +0,19 |
| −40 | −39,66 | +0,34 |
| −50 | −49,40 | +0,60 |
| −60 | −58,66 | +1,34 |
| −70 | −67,35 | +2,65 |
| −80 | −72,90 | +7,10 |

Generator aus: −76,29 dBm. Dämpfergenauigkeit nicht unabhängig bestimmt.
A0-Prüfung der unteren Grenze steht aus.

Vorläufig quantitativ geprüfter A1-Bereich: etwa −50 bis +10 dBm bei 1 MHz = 10 nW bis 10 mW. Keine garantierte Genauigkeit über alle Frequenzen.
Firmware-Hauptleitungsanzeige akzeptiert −65 bis +10 dBm am Detektor; das ist eine Anzeigegrenze, kein Genauigkeitsnachweis.

## Hauptleitung
P_Leitung,dBm = P_Detektor,dBm + Koppeldämpfung_dB.
| Kopplung dB | Untere Grenze bei −50 dBm | Obere bei +10 dBm |
|---:|---:|---:|
| 19 | 0,79 µW | 0,79 W |
| 20 | 1 µW | 1 W |
| 30 | 10 µW | 10 W |
| 40 | 100 µW | 100 W |
| 42 | 158 µW | 158 W |

19 dB ist die Nutzerangabe für den Eigenbau. Frequenzabhängige Kopplung beider Richtungen für genaue Wattmessung bestätigen.
Diese Umrechnung ist keine Hardware-Leistungsfreigabe. Koppler, Abschluss, Leitungen und Detektor müssen Spannung, Strom und Verluste vertragen.
Geplante Schottky-Erweiterung A2/A3 benötigt eigene Kennlinien und passend ausgelegte Auskopplung.
