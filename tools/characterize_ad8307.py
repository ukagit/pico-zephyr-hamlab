#!/usr/bin/env python3
"""Map FY6900 settings against one connected HamLab AD8307 input."""

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sweep_fy6900 import api, fy, mhz_to_hz


def voltage_list(value):
    try:
        levels = [Decimal(part.strip()) for part in value.split(',')]
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError('Volt-Einstellungen ungültig') from exc
    if not levels or any(not x.is_finite() or x <= 0 for x in levels):
        raise argparse.ArgumentTypeError('Volt-Einstellungen müssen positiv sein')
    return levels


def main():
    p = argparse.ArgumentParser(description='FY6900-Pegel/Frequenz gegen HamLab A0 oder A1 erfassen')
    p.add_argument('--host', required=True)
    p.add_argument('--input', required=True, choices=('a0', 'a1'),
                   help='hier ist das HF-Kabel tatsächlich angeschlossen')
    p.add_argument('--fy', type=Path,
                   default=Path('/home/ulrich/Dokumente/GitHub/workbench/cmd/fy'))
    p.add_argument('--fy-channel', type=int, choices=(1, 2), default=1)
    p.add_argument('--start-mhz', type=mhz_to_hz, default=1_000_000)
    p.add_argument('--stop-mhz', type=mhz_to_hz, default=1_000_000)
    p.add_argument('--step-mhz', type=mhz_to_hz, default=1_000_000)
    p.add_argument('--voltages', type=voltage_list, default=voltage_list('0.05,0.1,0.15,0.2'),
                   help='kommagetrennte FY --volts Einstellungen (keine gemessenen Vpp)')
    p.add_argument('--attenuation', type=int, default=0,
                   help='HamLab-ATT-Zustand; bei direkter FY-AD8307-Verbindung wirkungslos')
    p.add_argument('--samples', type=int, default=2)
    p.add_argument('--max-reported-dbm', type=float, default=10.0,
                   help='bei Überschreitung abbrechen (Standard +10 dBm Anzeige)')
    p.add_argument('--settle', type=float, default=0.15)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.suffix.lower() != '.csv' or args.output.exists():
        p.error('--output muss eine neue .csv-Datei sein')
    if not args.fy.is_file() or not args.fy.stat().st_mode & 0o111:
        p.error(f'FY-CLI fehlt oder ist nicht ausführbar: {args.fy}')
    if not 0 <= args.attenuation <= 30 or not 1 <= args.samples <= 50 or args.settle < 0:
        p.error('Dämpfung 0..30 dB, samples 1..50, settle >= 0')
    if args.start_mhz <= 0 or args.stop_mhz < args.start_mhz or args.stop_mhz > 60_000_000 or args.step_mhz <= 0:
        p.error('Frequenzen: 0 < Start <= Stop <= 60 MHz, Schritt > 0')
    frequencies = range(args.start_mhz, args.stop_mhz + 1, args.step_mhz)
    points = len(frequencies) * len(args.voltages)
    if points > 10_000:
        p.error(f'zu viele Messpunkte: {points}')

    base = f'http://{args.host}:8080'
    info = api(base, '/api/v1/info')
    version = info.get('version', '')
    if info.get('name') != 'hamlab' or version not in ('0.2.9', '0.2.10', '0.2.11', '0.2.12', '0.2.13', '0.3.0', '0.3.1', '0.3.2', '0.3.3', '0.3.4', '0.3.5', '0.3.6', '0.3.7'):
        raise RuntimeError(f'Erwartet HamLab 0.2.9–0.3.7: {info}')
    alignment = float(info.get('a1_alignment_db', 0.0))
    state = api(base, '/api/v1/config', {'attenuation_db': args.attenuation})
    if state.get('attenuation_db') != args.attenuation:
        raise RuntimeError(f'Dämpfung nicht bestätigt: {state}')
    print(f'{points} Stufen, HF an {args.input.upper()}, intern {args.attenuation} dB')
    print('FY --volts ist nur der Stellwert. Absolute dBm benötigen einen Referenzpegel an 50 Ω.')
    fields = ('utc', 'firmware_version', 'a1_alignment_db', 'rf_input', 'fy_frequency_hz', 'fy_volts_setting',
              'internal_attenuation_db', 'sample', 'channel', 'voltage_v',
              'reported_dbm', 'mean_dbm', 'measurement_valid')
    fy_started = False
    try:
        with args.output.open('x', newline='', encoding='utf-8') as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for freq in frequencies:
                for volts in args.voltages:
                    fy_started = True
                    fy(args.fy, args.fy_channel, 'set', '--wave', 'sine',
                       '--freq', freq, '--volts', str(volts), '--offset', 0, '--on')
                    time.sleep(args.settle)
                    readings = []
                    for _ in range(args.samples):
                        result = api(base, '/api/v1/measure')
                        if (not result.get('measurement_valid') or
                                result.get('attenuation_db') != args.attenuation or
                                len(result.get('channels', [])) != 2):
                            raise RuntimeError(f'ADS1115-Messung ungültig: {result}')
                        readings.append(result)
                    selected = 0 if args.input == 'a0' else 1
                    avg = statistics.mean(r['channels'][selected]['dbm'] for r in readings)
                    for sample, result in enumerate(readings, 1):
                        for channel in (0, 1):
                            value = result['channels'][channel]
                            writer.writerow(dict(utc=datetime.now(timezone.utc).isoformat(),
                                firmware_version=version, a1_alignment_db=f'{alignment:.4f}',
                                rf_input=args.input, fy_frequency_hz=freq,
                                fy_volts_setting=str(volts),
                                internal_attenuation_db=args.attenuation,
                                sample=sample, channel=channel,
                                voltage_v=value['voltage_v'],
                                reported_dbm=value['dbm'],
                                mean_dbm=f'{avg:.3f}' if channel == selected else '',
                                measurement_valid=True))
                    output.flush()
                    print(f'{freq / 1e6:g} MHz / FY {volts} V -> {args.input.upper()} {avg:+.3f} dBm', flush=True)
                    if avg > args.max_reported_dbm:
                        raise RuntimeError(f'Pegel {avg:+.3f} dBm über Grenze '
                                           f'{args.max_reported_dbm:+.1f} dBm; '
                                           'FY-Ausgang wird ausgeschaltet')
    finally:
        if fy_started:
            try:
                fy(args.fy, args.fy_channel, 'off')
                print('FY-Ausgang ausgeschaltet.')
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f'ACHTUNG: FY nicht sicher ausgeschaltet: {exc}', file=sys.stderr)
        try:
            api(base, '/api/v1/config', {'attenuation_db': 30})
        except RuntimeError as exc:
            print(f'ACHTUNG: HamLab-Dämpfung nicht zurückgesetzt: {exc}', file=sys.stderr)
    print(f'CSV: {args.output}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, KeyboardInterrupt, subprocess.TimeoutExpired) as exc:
        print(f'Abbruch: {exc}', file=sys.stderr)
        sys.exit(1)
