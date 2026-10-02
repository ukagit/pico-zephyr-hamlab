#!/usr/bin/env python3
"""Scalar SWR from FY6900/HamLab sweeps, with A0 forward and A1 reflected.

Use open and 50-ohm sweeps at the same generator setting as the DUT sweep.
The 50-ohm result estimates the measurement limit; it is not error correction.
"""
import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path


def load(path):
    points = {}
    settings = set()
    with path.open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            hz = int(row['fy_frequency_hz'])
            channel = int(row['channel'])
            settings.add((row['fy_channel'], row['fy_volts_setting'],
                          row['internal_attenuation_db']))
            # mean_dbm is repeated for each sample; keep one channel mean.
            value = float(row['mean_dbm'])
            if not math.isfinite(value):
                raise ValueError(f'{path}: ungültiger dBm-Wert bei {hz} Hz')
            old = points.setdefault(hz, {}).get(channel)
            if old is not None and abs(old - value) > 0.001:
                raise ValueError(f'{path}: widersprüchliche Mittelwerte bei {hz} Hz')
            points[hz][channel] = value
    if not points or any(set(row) != {0, 1} for row in points.values()) or len(settings) != 1:
        raise ValueError(f'{path}: unvollständige Frequenzen, Kanäle oder Generator-Einstellungen')
    return points, settings.pop()


def check_compatible(reference, candidate, label):
    if reference[1] != candidate[1] or set(reference[0]) != set(candidate[0]):
        raise ValueError(f'{label}: Frequenzraster oder FY6900/ATT-Einstellung passt nicht zur Offen-Referenz')


def plot_with_gnuplot(path, output, program, has_dut):
    script = '''set terminal pngcairo size 1100,650 enhanced font "Sans,12"
set output "''' + str(output).replace('"', '\\"') + '''"
set title "HamLab · skalare Rueckflussdaempfung"
set xlabel "Frequenz (MHz)"
set ylabel "Rueckflussdaempfung (dB)"
set grid
set key top right
set datafile separator comma
plot "''' + str(path).replace('"', '\\"') + '''" using ($1/1e6):7 with linespoints lw 2 title "50 Ohm: Messgrenze"''' + (''', \\
     "''' + str(path).replace('"', '\\"') + '''" using ($1/1e6):8 with linespoints lw 2 title "Pruefling"''' if has_dut else '') + '''
'''
    result = subprocess.run([program], input=script, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def main():
    ap = argparse.ArgumentParser(description='Skalares SWR mit Offen-Referenz und 50-Ohm-Messgrenze')
    ap.add_argument('--open', type=Path, required=True, help='Offen-Sweep A0 vorwärts, A1 rückwärts')
    ap.add_argument('--load', type=Path, required=True, help='50-Ohm-Sweep derselben Verdrahtung')
    ap.add_argument('--dut', type=Path, help='bereits gemessener Prüfling-Sweep')
    ap.add_argument('--measure-dut', action='store_true', help='Prüfling jetzt mit sweep_fy6900.py messen')
    ap.add_argument('--host', help='Pico-IP für --measure-dut')
    ap.add_argument('--fy', type=Path, help='FY6900-CLI für --measure-dut')
    ap.add_argument('--samples', type=int, default=2)
    ap.add_argument('--output', type=Path, default=Path('swr_auswertung.csv'))
    ap.add_argument('--plot-output', type=Path, help='PNG-Datei (standardmäßig gleicher Name wie CSV)')
    ap.add_argument('--gnuplot', default='gnuplot')
    ap.add_argument('--no-plot', action='store_true')
    args = ap.parse_args()
    if args.measure_dut and (not args.host or not args.dut):
        ap.error('--measure-dut braucht --host und --dut <neuer Dateiname>')
    if args.output.exists() or (args.measure_dut and args.dut.exists()):
        ap.error('Ausgabedatei existiert bereits')
    o = load(args.open)
    l = load(args.load)
    check_compatible(o, l, '50 Ohm')
    freq = sorted(o[0])
    if args.measure_dut:
        if len(freq) < 2 or len(set(b-a for a,b in zip(freq,freq[1:]))) != 1:
            ap.error('Für automatisches Messen ist ein gleichmäßiges Frequenzraster nötig')
        fy_channel, volts, attenuation = o[1]
        command = [sys.executable, str(Path(__file__).with_name('sweep_fy6900.py')),
                   '--host', args.host, '--channel', fy_channel, '--volts', volts,
                   '--attenuation', attenuation, '--samples', str(args.samples),
                   '--start-mhz', str(freq[0]/1e6), '--stop-mhz', str(freq[-1]/1e6),
                   '--step-mhz', str((freq[1]-freq[0])/1e6),
                   '--output', str(args.dut), '--no-plot']
        if args.fy: command += ['--fy', str(args.fy)]
        subprocess.run(command, check=True)
    d = load(args.dut) if args.dut else None
    if d: check_compatible(o, d, 'Prüfling')
    with args.output.open('x', newline='', encoding='utf-8') as stream:
        w = csv.writer(stream)
        w.writerow(['frequency_hz','open_a0_dbm','open_a1_dbm','open_delta_db',
                    'load_a0_dbm','load_a1_dbm','limit_rl_db','dut_rl_db',
                    'dut_swr','limit_reached','dut_a0_dbm','dut_a1_dbm'])
        for hz in freq:
            a,b=o[0][hz],l[0][hz]
            open_delta=a[1]-a[0]
            limit=open_delta-(b[1]-b[0])
            rl=swr=flag=''
            da0=da1=''
            if d:
                da0,da1=d[0][hz][0],d[0][hz][1]
                rl=open_delta-(da1-da0)
                flag='yes' if rl >= limit-3 else 'no'
                if 0 < rl < limit-3:
                    gamma=10**(-rl/20)
                    swr=(1+gamma)/(1-gamma)
                elif rl <= 0:
                    flag='invalid'
            w.writerow([hz,f'{a[0]:.3f}',f'{a[1]:.3f}',f'{open_delta:.3f}',
                        f'{b[0]:.3f}',f'{b[1]:.3f}',f'{limit:.3f}',
                        f'{rl:.3f}' if d else '',f'{swr:.3f}' if isinstance(swr,float) else '',
                        flag,da0,da1])
    print(f'Auswertung: {args.output}; A0 vorwärts, A1 rückwärts')
    for hz in (freq[0],freq[len(freq)//2],freq[-1]):
        a,b=o[0][hz],l[0][hz]
        print(f'{hz/1e6:g} MHz: Offen {a[1]-a[0]:+.2f} dB; '
              f'50-Ohm-Messgrenze {(a[1]-a[0])-(b[1]-b[0]):.2f} dB')
    if not args.no_plot:
        png=args.plot_output or args.output.with_suffix('.png')
        plot_with_gnuplot(args.output,png,args.gnuplot,bool(d))
        print(f'Plot: {png}')


if __name__ == '__main__':
    try: main()
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Abbruch: {exc}') from exc
