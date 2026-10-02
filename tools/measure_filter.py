#!/usr/bin/env python3
"""Two-pass splitter reference and filter insertion-loss measurement."""
import argparse
import csv
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sweep_fy6900 import api, fy, mhz_to_hz

FIELDS = ('utc', 'mode', 'firmware_version', 'a1_alignment_db',
          'fy_frequency_hz', 'fy_channel', 'fy_volts_setting',
          'internal_attenuation_db', 'samples', 'a0_dbm', 'a1_dbm',
          'a0_minus_a1_db', 'a0_voltage_v', 'a1_voltage_v')
RESULT_FIELDS = ('frequency_mhz', 'baseline_a0_minus_a1_db',
                 'dut_a0_minus_a1_db', 'insertion_loss_db',
                 'transmission_db', 'baseline_a0_dbm', 'baseline_a1_dbm',
                 'dut_a0_dbm', 'dut_a1_dbm')


def scan_stem(args):
    def mhz(hz):
        number = format(Decimal(hz) / Decimal(1_000_000), 'f')
        return (number.rstrip('0').rstrip('.') if '.' in number else number).replace('.', 'p')
    volts = format(Decimal(str(args.volts)), 'f').replace('.', 'p')
    return (f'filter_{mhz(args.start_mhz)}-{mhz(args.stop_mhz)}MHz_'
            f'step{mhz(args.step_mhz)}MHz_{volts}V_'
            f'ch{args.fy_channel}_att{args.attenuation}_s{args.samples}')


def read_sweep(path, expected):
    with path.open(newline='', encoding='utf-8') as inp:
        rows = list(csv.DictReader(inp))
    if not rows or not set(FIELDS).issubset(rows[0]):
        raise RuntimeError(f'Ungültige Messdatei: {path}')
    result = {}
    for row in rows:
        if row['mode'] != expected:
            raise RuntimeError(f'{path}: erwartet Modus {expected}')
        freq = int(row['fy_frequency_hz'])
        if freq in result:
            raise RuntimeError(f'{path}: doppelte Frequenz {freq}')
        result[freq] = row
    return result


def require_reference_points(reference, wanted):
    missing = sorted(wanted - set(reference))
    if missing:
        raise RuntimeError(f'{len(missing)} Frequenzpunkte fehlen in der Baseline, '
                           f'z. B. {missing[:8]} Hz. Baseline mit gleicher '
                           'oder feinerer Schrittweite neu messen.')


def plot_csv(path, png, gnuplot, interactive):
    data = repr(str(path.resolve()))
    image = repr(str(png.resolve()))
    base = ('set datafile separator comma\nset grid\n'
            'set xlabel "Frequenz (MHz)"\n'
            'set ylabel "Durchlasskurve (dB)"\n'
            'set key outside right top\n')
    line = f'plot {data} every ::1 using 1:5 with lines title "DUT A0 / Referenz A1"\n'
    cmd = ('set terminal pngcairo size 1200,700 enhanced font "Sans,11"\n'
           f'set output {image}\n' + base + line + 'unset output\n')
    proc = subprocess.run([gnuplot], input=cmd, text=True, capture_output=True,
                          timeout=30, check=False)
    if proc.returncode or not png.is_file():
        raise RuntimeError(f'Gnuplot: {proc.stderr.strip() or proc.stdout.strip()}')
    if interactive:
        cmd = ('set terminal qt\nset mouse\n'
               'set mouse mouseformat "f = %.4f MHz, Durchlass = %.3f dB"\n'
               + base + line + 'pause mouse close\n')
        proc = subprocess.run([gnuplot, '-persist'], input=cmd, text=True,
                              capture_output=True, check=False)
        if proc.returncode:
            raise RuntimeError(f'Gnuplot interaktiv: {proc.stderr.strip()}')


def main():
    p = argparse.ArgumentParser(description='Splitter-Abgleich und Filtermessung: DUT A0, Referenz A1')
    p.add_argument('--mode', choices=('baseline', 'dut', 'analyze'), required=True)
    p.add_argument('--host', default='192.168.178.69', help='HamLab-Adresse (Standard 192.168.178.69)')
    p.add_argument('--fy', type=Path, default=Path('/home/ulrich/Dokumente/GitHub/workbench/cmd/fy'))
    p.add_argument('--fy-channel', type=int, choices=(1, 2), default=1)
    p.add_argument('--volts', type=float, default=0.18, help='FY-Stellwert, keine kalibrierten Vpp')
    p.add_argument('--attenuation', type=int, default=0, help='HamLab-ATT-Status; direkter Messpfad: 0')
    p.add_argument('--start-mhz', type=mhz_to_hz, default=1_000_000)
    p.add_argument('--stop-mhz', type=mhz_to_hz, default=11_000_000)
    p.add_argument('--step-mhz', type=mhz_to_hz, default=100_000)
    p.add_argument('--samples', type=int, default=2)
    p.add_argument('--settle', type=float, default=0.15)
    p.add_argument('--max-reported-dbm', type=float, default=10.0)
    p.add_argument('--baseline', type=Path, help='Referenz-CSV ohne DUT (für dut/analyze)')
    p.add_argument('--dut', type=Path, help='DUT-CSV für analyze')
    p.add_argument('--output', type=Path, help='neue CSV-Datei; für baseline/dut automatisch')
    p.add_argument('--plot-output', type=Path, help='PNG-Ergebnis (dut/analyze)')
    p.add_argument('--gnuplot', default='gnuplot')
    p.add_argument('--interactive', action='store_true')
    args = p.parse_args()
    if args.mode == 'analyze' and args.output is None:
        p.error('--output ist bei --mode analyze erforderlich')
    if args.mode in ('baseline', 'dut'):
        stem = scan_stem(args)
        if args.mode == 'dut' and args.baseline is None:
            args.baseline = Path(stem + '_baseline.csv')
        if args.output is None:
            if args.mode == 'baseline':
                args.output = Path(stem + '_baseline.csv')
            else:
                for index in range(1, 1000):
                    candidate = Path(f'{stem}_dut_{index:03d}.csv')
                    if not candidate.exists() and not candidate.with_name(candidate.stem + '_loss.csv').exists():
                        args.output = candidate
                        break
                if args.output is None:
                    p.error('Keine freie DUT-Dateinummer gefunden')
    if args.output.suffix.lower() != '.csv' or args.output.exists():
        p.error('--output muss eine neue .csv-Datei sein')
    if args.plot_output and (args.plot_output.suffix.lower() != '.png' or args.plot_output.exists()):
        p.error('--plot-output muss eine neue .png-Datei sein')
    if args.mode in ('dut', 'analyze') and (not args.baseline or not args.baseline.is_file()):
        p.error('--baseline muss auf eine vorhandene Referenz-CSV zeigen')

    if args.mode == 'analyze':
        if not args.dut or not args.dut.is_file():
            p.error('--dut muss auf eine vorhandene DUT-CSV zeigen')
        baseline = read_sweep(args.baseline, 'baseline')
        dut = read_sweep(args.dut, 'dut')
        require_reference_points(baseline, set(dut))
        keys = ('a1_alignment_db', 'fy_channel',
                'fy_volts_setting', 'internal_attenuation_db', 'samples')
        with args.output.open('x', newline='', encoding='utf-8') as out:
            writer = csv.DictWriter(out, fieldnames=RESULT_FIELDS)
            writer.writeheader()
            for freq in sorted(dut):
                b, d = baseline[freq], dut[freq]
                if any(b[k] != d[k] for k in keys):
                    raise RuntimeError(f'Messparameter bei {freq} Hz verschieden: {keys}')
                db = float(b['a0_minus_a1_db'])
                dd = float(d['a0_minus_a1_db'])
                loss = db - dd
                writer.writerow(dict(frequency_mhz=f'{freq / 1e6:.6f}',
                    baseline_a0_minus_a1_db=f'{db:.4f}',
                    dut_a0_minus_a1_db=f'{dd:.4f}',
                    insertion_loss_db=f'{loss:.4f}', transmission_db=f'{-loss:.4f}',
                    baseline_a0_dbm=b['a0_dbm'], baseline_a1_dbm=b['a1_dbm'],
                    dut_a0_dbm=d['a0_dbm'], dut_a1_dbm=d['a1_dbm']))
        print(f'Filterkurve: {args.output}')
        png = args.plot_output or args.output.with_suffix('.png')
        if png.exists():
            raise RuntimeError(f'PNG existiert bereits: {png}')
        plot_csv(args.output, png, args.gnuplot, args.interactive)
        print(f'Plot: {png}')
        return

    if not args.host or not args.fy.is_file() or not args.fy.stat().st_mode & 0o111:
        p.error('Für den Sweep --host und ausführbares --fy erforderlich')
    if (not 0 < args.volts <= 3 or not 0 <= args.attenuation <= 30 or
        not 1 <= args.samples <= 100 or args.settle < 0 or
        not 0 < args.start_mhz <= args.stop_mhz <= 60_000_000 or
        args.step_mhz <= 0 or
        (args.stop_mhz-args.start_mhz)//args.step_mhz+1 > 10_000):
        p.error('Ungültige Pegel-, Dämpfungs-, Frequenz- oder Abtastparameter')
    base = f'http://{args.host}:8080'
    info = api(base, '/api/v1/info')
    if info.get('name') != 'hamlab' or info.get('version') not in ('0.2.9', '0.2.10', '0.2.11', '0.2.12', '0.2.13', '0.3.0', '0.3.1', '0.3.2', '0.3.3', '0.3.4', '0.3.5', '0.3.6', '0.3.7'):
        raise RuntimeError(f'HamLab 0.2.9–0.3.7 erforderlich: {info}')
    alignment = float(info.get('a1_alignment_db', 0.0))
    if args.mode == 'dut':
        previous = read_sweep(args.baseline, 'baseline')
        wanted = set(range(args.start_mhz, args.stop_mhz + 1, args.step_mhz))
        require_reference_points(previous, wanted)
        example = previous[min(wanted)]
        config = dict(a1_alignment_db=f'{alignment:.4f}',
                      fy_channel=str(args.fy_channel), fy_volts_setting=str(args.volts),
                      internal_attenuation_db=str(args.attenuation), samples=str(args.samples))
        if any(example[k] != v for k, v in config.items()):
            raise RuntimeError(f'Messparameter passen nicht zur Baseline: {config}')
    state = api(base, '/api/v1/config', {'attenuation_db': args.attenuation})
    if state.get('attenuation_db') != args.attenuation:
        raise RuntimeError(f'Dämpfung nicht bestätigt: {state}')
    print(f'{args.mode}: FY CH{args.fy_channel} {args.volts} V; '
          f'{args.start_mhz/1e6:g}–{args.stop_mhz/1e6:g} MHz; '
          f'A0 Testzweig, A1 Referenzzweig')
    fy_started = False
    try:
        with args.output.open('x', newline='', encoding='utf-8') as out:
            writer = csv.DictWriter(out, fieldnames=FIELDS)
            writer.writeheader()
            for freq in range(args.start_mhz, args.stop_mhz + 1, args.step_mhz):
                fy_started = True
                fy(args.fy, args.fy_channel, 'set', '--wave', 'sine', '--freq', freq,
                   '--volts', args.volts, '--offset', 0, '--on')
                time.sleep(args.settle)
                readings = []
                for _ in range(args.samples):
                    state = api(base, '/api/v1/measure')
                    if not state.get('measurement_valid') or len(state.get('channels', [])) != 2 or state.get('attenuation_db') != args.attenuation:
                        raise RuntimeError(f'Fehlerhafte Messung bei {freq} Hz: {state}')
                    readings.append(state)
                levels = [statistics.mean(r['channels'][c]['dbm'] for r in readings) for c in (0, 1)]
                if max(levels) > args.max_reported_dbm:
                    raise RuntimeError(f'{freq/1e6:g} MHz: Pegel über +{args.max_reported_dbm:g} dBm')
                row = dict(utc=datetime.now(timezone.utc).isoformat(), mode=args.mode,
                    firmware_version=info['version'], a1_alignment_db=f'{alignment:.4f}',
                    fy_frequency_hz=freq, fy_channel=args.fy_channel,
                    fy_volts_setting=str(args.volts), internal_attenuation_db=args.attenuation,
                    samples=args.samples, a0_dbm=f'{levels[0]:.4f}', a1_dbm=f'{levels[1]:.4f}',
                    a0_minus_a1_db=f'{levels[0]-levels[1]:.4f}',
                    a0_voltage_v=f'{statistics.mean(r["channels"][0]["voltage_v"] for r in readings):.5f}',
                    a1_voltage_v=f'{statistics.mean(r["channels"][1]["voltage_v"] for r in readings):.5f}')
                writer.writerow(row)
                out.flush()
                print(f'{freq/1e6:g} MHz A0−A1 {levels[0]-levels[1]:+.3f} dB', flush=True)
    finally:
        if fy_started:
            try:
                fy(args.fy, args.fy_channel, 'off')
                print('FY-Ausgang aus')
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f'ACHTUNG: FY-Ausgang nicht sicher aus: {exc}', file=sys.stderr)
        try:
            api(base, '/api/v1/config', {'attenuation_db': 30})
        except RuntimeError as exc:
            print(f'ACHTUNG: HamLab-ATT nicht zurückgesetzt: {exc}', file=sys.stderr)
    print(f'CSV: {args.output}')
    if args.mode == 'dut':
        result = args.output.with_name(args.output.stem + '_loss.csv')
        if result.exists():
            raise RuntimeError(f'Ergebnisdatei existiert bereits: {result}')
        args2 = [sys.executable, __file__, '--mode', 'analyze', '--baseline', str(args.baseline),
                 '--dut', str(args.output), '--output', str(result), '--gnuplot', args.gnuplot]
        if args.plot_output:
            args2 += ['--plot-output', str(args.plot_output)]
        if args.interactive:
            args2 += ['--interactive']
        subprocess.run(args2, check=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        print(f'Abbruch: {exc}', file=sys.stderr)
        sys.exit(1)
