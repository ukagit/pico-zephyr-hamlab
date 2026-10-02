#!/usr/bin/env python3
"""Sweep FY6900 CH1 and record both HamLab AD8307 channels over HTTP."""

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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('ascii')
    request = Request(base + path, data=data,
                      method='GET' if data is None else 'POST')
    if data is not None:
        request.add_header('Content-Type', 'application/json')
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f'{path}: {exc}') from exc


def fy(command, channel, *args):
    result = subprocess.run([str(command), '-c', str(channel), *map(str, args)],
                            text=True, capture_output=True, timeout=15,
                            check=False)
    if result.returncode:
        raise RuntimeError(f'FY6900 ({result.returncode}): '
                           f'{result.stderr.strip() or result.stdout.strip()}')
    return result.stdout.strip()


def mhz_to_hz(value):
    try:
        hz = Decimal(value) * 1_000_000
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError('MHz-Zahl ungültig') from exc
    if not hz.is_finite() or hz != hz.to_integral_value():
        raise argparse.ArgumentTypeError('Frequenz und Schrittweite müssen ganze Hz ergeben')
    return int(hz)


def make_plot(csv_path, png_path, gnuplot, channels='both', ymin=None, ymax=None,
              interactive=False):
    summary_path = csv_path.with_name(csv_path.stem + '_summary.csv')
    by_frequency = {}
    with csv_path.open(newline='', encoding='utf-8') as inp:
        for row in csv.DictReader(inp):
            if int(row['sample']) != 1:
                continue
            freq = int(row['fy_frequency_hz'])
            channel = int(row['channel'])
            by_frequency.setdefault(freq, {})[channel] = float(row['mean_dbm'])
    if not by_frequency:
        raise RuntimeError('CSV enthält keine Messpunkte')
    with summary_path.open('w', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow(('frequency_mhz', 'a0_dbm', 'a1_dbm', 'a1_minus_a0_db'))
        count = 0
        for freq, channel_values in sorted(by_frequency.items()):
            if 0 not in channel_values or 1 not in channel_values:
                continue
            writer.writerow((f'{freq / 1e6:.6f}', f'{channel_values[0]:.3f}',
                             f'{channel_values[1]:.3f}',
                             f'{channel_values[1]-channel_values[0]:.3f}'))
            count += 1
    if count == 0:
        raise RuntimeError('CSV enthält keine vollständigen A0/A1-Paare')

    # Numeric columns in the summary need no conditional Gnuplot expressions.
    data = json.dumps(str(summary_path.resolve()))
    image = json.dumps(str(png_path.resolve()))
    yrange = '' if ymin is None and ymax is None else f'set yrange [{"*" if ymin is None else ymin}:{"*" if ymax is None else ymax}]\n'
    plots = []
    if channels in ('both', 'a0'):
        plots.append(f'{data} using 1:2 with linespoints title "A0"')
    if channels in ('both', 'a1'):
        plots.append(f'{data} using 1:3 with linespoints title "A1"')
    curves = ', '.join(plots)
    if channels == 'both':
        body = f'''set multiplot layout 2,1 title "FY6900 / HamLab: Frequenzgang A0 und A1"
set ylabel "Pegel (dBm)"
{yrange}plot {curves}
set autoscale y
set xlabel "FY6900-Frequenz (MHz)"
set ylabel "A1 - A0 (dB)"
plot {data} using 1:4 with linespoints title "Differenz"
unset multiplot
'''
    else:
        body = f'set xlabel "FY6900-Frequenz (MHz)"\nset ylabel "Pegel (dBm)"\n{yrange}plot {curves}\n'
    commands = f'''set terminal pngcairo size 1200,750 enhanced font "Sans,11"
set output {image}
set datafile separator comma
set grid
set key outside right top
{body}
unset output
'''
    result = subprocess.run([gnuplot], input=commands, text=True,
                            capture_output=True, timeout=30, check=False)
    if result.returncode or not png_path.is_file():
        raise RuntimeError(f'Gnuplot: {result.stderr.strip() or result.stdout.strip()}')
    if interactive:
        # Mouse coordinates are unavailable in a multiplot: use one 2D graph.
        mouse_commands = f'''set terminal qt
set mouse
set mouse mouseformat "f = %.4f MHz, P = %.3f dBm"
set datafile separator comma
set grid
set key outside right top
set xlabel "FY6900-Frequenz (MHz)"
set ylabel "Pegel (dBm)"
{yrange}plot {curves}
pause mouse close
'''
        result = subprocess.run([gnuplot, '-persist'], input=mouse_commands,
                                text=True, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError(f'Gnuplot interaktiv: {result.stderr.strip()}')


def main():
    parser = argparse.ArgumentParser(description='FY6900 MHz-Sweep: HamLab A0/A1 messen und plotten')
    parser.add_argument('--host', help='IP des HamLab Pico 2 W')
    parser.add_argument('--fy', type=Path,
                        default=Path('/home/ulrich/Dokumente/GitHub/workbench/cmd/fy'),
                        help='Pfad zum ausführbaren Workbench-Kommando ./cmd/fy')
    parser.add_argument('--channel', type=int, choices=(1, 2), default=1,
                        help='FY6900-Kanal (Standard 1)')
    parser.add_argument('--volts', type=float, default=2.2,
                        help='FY6900 --volts, nicht automatisch ein gemessener Vpp-Wert')
    parser.add_argument('--attenuation', type=int, default=20,
                        help='interne HamLab-Dämpfung in dB (Standard 20)')
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--start-mhz', type=mhz_to_hz, default=1_000_000)
    parser.add_argument('--stop-mhz', type=mhz_to_hz, default=5_000_000)
    parser.add_argument('--step-mhz', type=mhz_to_hz, default=1_000_000)
    parser.add_argument('--settle', type=float, default=0.6,
                        help='Sekunden nach jedem Frequenzwechsel')
    parser.add_argument('--interval', type=float, default=0.15)
    parser.add_argument('--output', type=Path, default=Path('fy6900_1-5mhz.csv'))
    parser.add_argument('--plot-output', type=Path, help='PNG-Datei (Standard: gleicher Name wie CSV)')
    parser.add_argument('--gnuplot', default='gnuplot', help='Gnuplot-Programm')
    parser.add_argument('--no-plot', action='store_true', help='nur CSV schreiben')
    parser.add_argument('--plot-only', action='store_true', help='vorhandene CSV plotten, ohne FY/HamLab anzusprechen')
    parser.add_argument('--channels', choices=('both', 'a0', 'a1'), default='both',
                        help='Kurvenauswahl im Plot (Standard beide)')
    parser.add_argument('--ymin-dbm', type=float, help='untere Grenze der Pegelachse')
    parser.add_argument('--ymax-dbm', type=float, help='obere Grenze der Pegelachse')
    parser.add_argument('--interactive', action='store_true',
                        help='zusätzlich interaktiven Qt-Plot mit Maus-Cursor öffnen')
    args = parser.parse_args()
    if args.output.suffix.lower() != '.csv':
        parser.error('--output muss eine CSV-Datei sein; für PNG --plot-output verwenden')
    if args.plot_output is not None and args.plot_output.suffix.lower() != '.png':
        parser.error('--plot-output muss eine PNG-Datei sein')
    if (args.ymin_dbm is not None and args.ymax_dbm is not None
            and args.ymin_dbm >= args.ymax_dbm):
        parser.error('--ymin-dbm muss kleiner als --ymax-dbm sein')
    png_path = args.plot_output or args.output.with_suffix('.png')
    if args.plot_only:
        if not args.output.is_file():
            parser.error(f'CSV fehlt: {args.output}')
        try:
            make_plot(args.output, png_path, args.gnuplot, args.channels,
                      args.ymin_dbm, args.ymax_dbm, args.interactive)
        except UnicodeError as exc:
            parser.error(f'--output ist keine lesbare UTF-8-CSV: {exc}')
        print(f'Plot gespeichert: {png_path}')
        return
    if not args.host:
        parser.error('--host ist für eine neue Messung erforderlich')
    if not args.fy.is_file() or not args.fy.stat().st_mode & 0o111:
        parser.error(f'FY-Kommando fehlt oder ist nicht ausführbar: {args.fy}')
    if not 0 <= args.attenuation <= 30 or not 1 <= args.samples <= 100:
        parser.error('attenuation muss 0..30 dB, samples 1..100 sein')
    if args.volts <= 0 or args.settle < 0 or args.interval < 0:
        parser.error('volts muss > 0 und Wartezeiten müssen >= 0 sein')
    if args.output.exists():
        parser.error(f'Ausgabedatei existiert bereits: {args.output}')
    if args.start_mhz <= 0 or args.stop_mhz < args.start_mhz or args.step_mhz <= 0:
        parser.error('MHz: Start > 0, Stop >= Start und Schritt > 0 erforderlich')
    points = (args.stop_mhz - args.start_mhz) // args.step_mhz + 1
    if points > 10_000:
        parser.error(f'{points} Messpunkte sind zu viele (maximal 10000)')
    if not args.no_plot and png_path.exists():
        parser.error(f'Plot-Datei existiert bereits: {png_path}')

    base = f'http://{args.host}:8080'
    info = api(base, '/api/v1/info')
    if info.get('name') != 'hamlab' or info.get('version') not in ('0.2.9', '0.2.10', '0.2.11', '0.2.12', '0.2.13', '0.3.0', '0.3.1', '0.3.2', '0.3.3', '0.3.4', '0.3.5', '0.3.6', '0.3.7'):
        raise RuntimeError(f'Erwartet HamLab 0.2.9–0.3.7, erhalten: {info}')
    state = api(base, '/api/v1/config', {'attenuation_db': args.attenuation})
    if state.get('attenuation_db') != args.attenuation:
        raise RuntimeError(f'Dämpfung nicht bestätigt: {state}')
    print(f'HamLab {args.host} v{info["version"]}; FY6900 CH{args.channel}, '
          f'{args.volts} V Einstellung; intern {args.attenuation} dB')
    print('HamLab-DDS bleibt unverändert. Beide Splitter-Ausgänge an A0/A1 anschließen.')
    print(f'{points} Messpunkte von {args.start_mhz / 1e6:g} bis '
          f'{args.stop_mhz / 1e6:g} MHz; Schritt {args.step_mhz / 1e6:g} MHz')

    columns = ('utc', 'fy_frequency_hz', 'fy_channel', 'fy_volts_setting',
               'hamlab_dds_frequency_hz', 'internal_attenuation_db',
               'sample', 'channel', 'voltage_v', 'dbm', 'mw', 'vpp',
               'mean_voltage_v', 'mean_dbm', 'delta_a1_minus_a0_db')
    started_fy = False
    try:
        with args.output.open('x', newline='', encoding='utf-8') as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            for freq in range(args.start_mhz, args.stop_mhz + 1, args.step_mhz):
                # The selected attenuation is set before enabling the generator.
                started_fy = True
                reply = fy(args.fy, args.channel, 'set', '--wave', 'sine',
                           '--freq', freq, '--volts', args.volts,
                           '--offset', 0, '--on')
                if reply:
                    print(f'FY {freq / 1e6:g} MHz: {reply}')
                time.sleep(args.settle)
                readings = []
                for sample in range(1, args.samples + 1):
                    result = api(base, '/api/v1/measure')
                    if not result.get('measurement_valid') or len(result.get('channels', [])) != 2:
                        raise RuntimeError(f'Messung ungültig bei {freq} Hz: {result}')
                    if result.get('attenuation_db') != args.attenuation:
                        raise RuntimeError(f'HamLab-Dämpfung während Sweep geändert: {result}')
                    readings.append(result)
                    if sample < args.samples:
                        time.sleep(args.interval)
                mean_dbm = [statistics.mean(r['channels'][ch]['dbm'] for r in readings)
                            for ch in (0, 1)]
                delta = mean_dbm[1] - mean_dbm[0]
                for ch in (0, 1):
                    mean_v = statistics.mean(r['channels'][ch]['voltage_v'] for r in readings)
                    for sample, result in enumerate(readings, 1):
                        value = result['channels'][ch]
                        writer.writerow(dict(utc=datetime.now(timezone.utc).isoformat(),
                            fy_frequency_hz=freq, fy_channel=args.channel,
                            fy_volts_setting=args.volts,
                            hamlab_dds_frequency_hz=result['frequency_hz'],
                            internal_attenuation_db=args.attenuation, sample=sample,
                            channel=ch, voltage_v=value['voltage_v'], dbm=value['dbm'],
                            mw=value['mw'], vpp=value['vpp'],
                            mean_voltage_v=f'{mean_v:.6f}',
                            mean_dbm=f'{mean_dbm[ch]:.3f}',
                            delta_a1_minus_a0_db=f'{delta:.3f}'))
                out.flush()
                print(f'{freq / 1e6:g} MHz | A0 {mean_dbm[0]:+.3f} dBm | '
                      f'A1 {mean_dbm[1]:+.3f} dBm | A1-A0 {delta:+.3f} dB')
    finally:
        if started_fy:
            try:
                fy(args.fy, args.channel, 'off')
                print('FY6900-Ausgang ausgeschaltet.')
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f'ACHTUNG: FY6900-Ausgang nicht sicher ausgeschaltet: {exc}', file=sys.stderr)
        try:
            api(base, '/api/v1/config', {'attenuation_db': 30})
        except RuntimeError as exc:
            print(f'ACHTUNG: HamLab-Dämpfung nicht auf 30 dB gesetzt: {exc}', file=sys.stderr)
    print(f'CSV gespeichert: {args.output}')
    if not args.no_plot:
        try:
            make_plot(args.output, png_path, args.gnuplot, args.channels,
                      args.ymin_dbm, args.ymax_dbm, args.interactive)
            print(f'Plot gespeichert: {png_path}')
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f'Plot konnte nicht erstellt werden: {exc}. CSV ist vorhanden.', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, KeyboardInterrupt, subprocess.TimeoutExpired) as exc:
        print(f'Abbruch: {exc}', file=sys.stderr)
        sys.exit(1)
