#!/usr/bin/env python3
"""Collect AD8307 calibration points over HamLab HTTP JSON API.

External attenuation is selected manually; the internal PE4302 is swept
through the *currently implemented* integer 0..30 dB range. No firmware
calibration is modified by this program.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('ascii')
    request = Request(base + path, data=data, method='GET' if data is None else 'POST')
    if data is not None:
        request.add_header('Content-Type', 'application/json')
    try:
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f'{path}: {exc}') from exc
    return result


def levels(value, minimum, maximum):
    result = [int(item.strip()) for item in value.split(',')]
    if not result or len(set(result)) != len(result) or any(not minimum <= n <= maximum for n in result):
        raise argparse.ArgumentTypeError(f'kommagetrennte ganze dB zwischen {minimum} und {maximum}, ohne Duplikate')
    return result


def main():
    parser = argparse.ArgumentParser(description='HamLab: A0/A1-Messreihe mit manuellen externen Dämpfungsstufen')
    parser.add_argument('--host', required=True, help='Pico-IP oder Hostname')
    parser.add_argument('--external', default='0,20,40,60', help='externe Stufen in dB (Standard: 0,20,40,60)')
    parser.add_argument('--internal', default='30,25,20,15,10', help='interne Stufen in dB (Standard: 30,25,20,15,10)')
    parser.add_argument('--samples', type=int, default=5, help='Messungen pro Stufe')
    parser.add_argument('--settle', type=float, default=0.3, help='Wartezeit nach Dämpfungswechsel in s')
    parser.add_argument('--interval', type=float, default=0.1, help='Pause zwischen Messungen in s')
    parser.add_argument('--source-dbm', type=float, help='gemessener Pegel vor beiden Dämpfungsgliedern an 50 Ohm')
    parser.add_argument('--output', type=Path, default=Path('ad8307_calibration.csv'))
    args = parser.parse_args()
    external = levels(args.external, 0, 200)
    internal = levels(args.internal, 0, 30)
    if args.samples < 1 or args.samples > 100 or args.settle < 0 or args.interval < 0:
        parser.error('samples muss 1..100 sein; Wartezeiten müssen >= 0 sein')
    base = 'http://' + args.host + ':8080'
    state = api(base, '/api/v1/state')
    if state.get('name') != 'hamlab':
        parser.error('Gegenstelle ist kein HamLab')
    print(f"HamLab {args.host}, DDS {state['frequency_hz']} Hz. CSV: {args.output}")
    print('Interne Stufen: ' + ', '.join(map(str, internal)) + ' dB')
    print('Sollwerte sind nominal; Einfügedämpfung und 50-Ohm-Abschluss separat prüfen.')
    fields = ['utc', 'frequency_hz', 'external_db', 'internal_db', 'nominal_total_db',
              'nominal_input_dbm', 'sample', 'channel', 'voltage_v', 'reported_dbm',
              'mean_voltage_v', 'mean_reported_dbm', 'valid']
    # Avoid accidental truncation of existing measurements.
    with args.output.open('x', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        # Highest attenuation before the user changes any RF connection.
        api(base, '/api/v1/config', {'attenuation_db': 30})
        try:
            for ext in external:
                input(f'Extern {ext} dB einstellen, HF-Aufbau prüfen, dann Enter drücken ... ')
                for att in internal:
                    if args.source_dbm is not None and args.source_dbm - ext - att > 10:
                        print(f'Überspringe {ext}+{att} dB: nominaler Eingang über +10 dBm')
                        continue
                    reply = api(base, '/api/v1/config', {'attenuation_db': att})
                    if reply.get('attenuation_db') != att:
                        raise RuntimeError(f'Dämpfung nicht bestätigt: {reply}')
                    time.sleep(args.settle)
                    readings = []
                    for sample in range(1, args.samples + 1):
                        result = api(base, '/api/v1/measure')
                        if not result.get('measurement_valid') or len(result.get('channels', [])) != 2:
                            raise RuntimeError(f'ADS1115-Messung ungültig: {result}')
                        readings.append(result)
                        if sample < args.samples:
                            time.sleep(args.interval)
                    nominal = None if args.source_dbm is None else args.source_dbm - ext - att
                    for ch in (0, 1):
                        values = [r['channels'][ch] for r in readings]
                        mean_v = statistics.mean(v['voltage_v'] for v in values)
                        mean_dbm = statistics.mean(v['dbm'] for v in values)
                        for sample, value in enumerate(values, 1):
                            writer.writerow(dict(utc=datetime.now(timezone.utc).isoformat(),
                                frequency_hz=readings[sample-1]['frequency_hz'],
                                external_db=ext, internal_db=att, nominal_total_db=ext+att,
                                nominal_input_dbm='' if nominal is None else f'{nominal:.4f}',
                                sample=sample, channel=ch, voltage_v=value['voltage_v'],
                                reported_dbm=value['dbm'], mean_voltage_v=f'{mean_v:.6f}',
                                mean_reported_dbm=f'{mean_dbm:.3f}', valid=True))
                        print(f'extern {ext:>2} + intern {att:>2} dB | A{ch}: {mean_v:.5f} V, {mean_dbm:.2f} dBm')
                    output.flush()
        finally:
            # Keep RF level low when the measurement ends or an error occurs.
            try:
                api(base, '/api/v1/config', {'attenuation_db': 30})
                print('Interne Dämpfung zum Abschluss auf 30 dB gesetzt.')
            except RuntimeError as exc:
                print(f'ACHTUNG: Dämpfung konnte nicht auf 30 dB gesetzt werden: {exc}', file=sys.stderr)
    print(f'Fertig: {args.output}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyboardInterrupt, FileExistsError) as exc:
        print(f'Abbruch: {exc}', file=sys.stderr)
        sys.exit(1)
