#!/usr/bin/env python3
"""Fit P_dBm = slope * ADS1115_voltage + intercept from a HamLab CSV."""
import argparse
import csv
import math
from collections import defaultdict


def fit(points):
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    xx = sum((x-mx)**2 for x, _ in points)
    if xx < 1e-10:
        raise ValueError('ADC-Spannungen ändern sich nicht genügend')
    slope = sum((x-mx)*(y-my) for x, y in points)/xx
    intercept = my-slope*mx
    errors = [slope*x+intercept-y for x, y in points]
    rms = math.sqrt(sum(e*e for e in errors)/n)
    return slope, intercept, rms, max(abs(e) for e in errors)


def main():
    ap = argparse.ArgumentParser(description='Lineare AD8307-Kalibriergerade aus der HamLab-Messreihe')
    ap.add_argument('csv_file')
    ap.add_argument('--source-dbm', type=float, help='Referenzpegel vor allen Dämpfungsgliedern, für CSV ohne Sollpegel')
    ap.add_argument('--max-total-db', type=float, default=65, help='maximale Gesamtdämpfung für Fit (Standard 65 dB)')
    ap.add_argument('--min-dbm', type=float, default=-65, help='untere Fit-Grenze (Standard -65)')
    ap.add_argument('--max-dbm', type=float, default=15, help='obere Fit-Grenze (Standard +15)')
    ap.add_argument('--channel', choices=('0', '1', 'both'), default='both', help='auszuwertender ADS1115-Kanal')
    args = ap.parse_args()
    groups = defaultdict(list)
    with open(args.csv_file, newline='', encoding='utf-8') as file:
        for row in csv.DictReader(file):
            external = float(row['external_db'])
            internal = float(row['internal_db'])
            if external + internal > args.max_total_db:
                continue
            if row['nominal_input_dbm']:
                power = float(row['nominal_input_dbm'])
            elif args.source_dbm is not None:
                power = args.source_dbm - external - internal
            else:
                ap.error('CSV ohne Sollpegel: --source-dbm angeben')
            key = (row['channel'], row['external_db'], row['internal_db'])
            groups[key].append((float(row['voltage_v']), power))
    for ch in (('0', '1') if args.channel == 'both' else (args.channel,)):
        points=[]
        for (channel, ext, att), values in groups.items():
            if channel != ch:
                continue
            y = values[0][1]
            if args.min_dbm <= y <= args.max_dbm:
                points.append((sum(v for v,_ in values)/len(values), y))
        if len(points)<3:
            print(f'A{ch}: Nur {len(points)} gültige Pegel, mindestens 3 nötig')
            continue
        span = max(x for x, _ in points) - min(x for x, _ in points)
        if span < 0.1:
            print(f'A{ch}: Keine Kalibrierung: ADC-Spannungsbereich nur {span:.5f} V')
            continue
        try:
            slope, intercept, rms, maximum = fit(points)
        except ValueError as exc:
            print(f'A{ch}: {exc}')
            continue
        if not 20 <= slope <= 80 or rms > 2:
            print(f'A{ch}: Keine plausible Kalibrierung: Steigung {slope:.2f} dB/V, RMS {rms:.2f} dB')
            continue
        print(f'A{ch}: {len(points)} Stufen; P_dBm = {slope:.5f} * U_ADC_V + ({intercept:.5f})')
        print(f'    Residuen: RMS {rms:.3f} dB, Maximum {maximum:.3f} dB; bisher 40 dB/V')
        print('    Sollpegel setzt genaue FY6900-Pegel und Dämpfungen bei 50 Ohm voraus.')


if __name__ == '__main__':
    main()
