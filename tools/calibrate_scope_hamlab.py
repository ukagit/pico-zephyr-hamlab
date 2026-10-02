#!/usr/bin/env python3
"""FY6900 settings + SDS status reference + HamLab readings; no firmware edits."""
import argparse
import csv
import json
import math
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def run(command):
    r = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or 'CLI fehlgeschlagen')
    return r.stdout


def quantity(text, unit):
    match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([munµkMG]?)' + unit + r'\s*', text)
    if not match:
        raise RuntimeError(f'Scope-Wert unlesbar: {text!r}')
    scales = {'': 1, 'm': 1e-3, 'u': 1e-6, 'µ': 1e-6, 'n': 1e-9, 'k': 1e3, 'M': 1e6, 'G': 1e9}
    return float(match[1]) * scales[match[2]]


def scope_read(text, channel):
    for line in text.splitlines():
        if re.match(rf'\s*CH{channel}:', line):
            match = re.search(r'RMS=(.*?)\s+Vpp=(.*?)\s+Freq=(.*?)\s*$', line)
            if not match:
                break
            return quantity(match[1], 'V'), quantity(match[2], 'V'), quantity(match[3], 'Hz')
    raise RuntimeError(f'Kein gültiger CH{channel}-Status vom SDS: {text}')


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return json.load(response)


def numbers(value):
    result = [float(x) for x in value.split(',')]
    if not result or any(not math.isfinite(x) or x <= 0 for x in result):
        raise argparse.ArgumentTypeError('Positive Zahlen, durch Kommas getrennt')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='192.168.178.69')
    p.add_argument('--input', choices=['a0', 'a1'], required=True)
    p.add_argument('--fy', type=Path, default=Path('/home/ulrich/Dokumente/GitHub/workbench/cmd/fy'))
    p.add_argument('--sds', type=Path, default=Path('/home/ulrich/Dokumente/GitHub/workbench/cmd/sds'))
    p.add_argument('--fy-channel', type=int, choices=[1, 2], default=1)
    p.add_argument('--scope-channel', type=int, choices=[1, 2], default=1)
    p.add_argument('--frequencies-mhz', type=numbers, default=numbers('0.1,1,7'))
    p.add_argument('--voltages', type=numbers, default=numbers('0.2,0.4,0.5,0.63'))
    p.add_argument('--samples', type=int, default=3)
    p.add_argument('--settle', type=float, default=1)
    p.add_argument('--resistance', type=float, default=50)
    p.add_argument('--max-vpp', type=float, default=1)
    p.add_argument('--max-fy-volts', type=float, default=1,
                   help='Obergrenze FY-Stellwert, explizit bis 4 V freigeben')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if not 1 <= args.samples <= 50 or args.settle < 0 or args.resistance <= 0 or args.max_vpp <= 0:
        p.error('samples 1..50; settle >= 0; resistance und max-vpp > 0')
    if not math.isfinite(args.max_fy_volts) or not 0 < args.max_fy_volts <= 4 or not math.isfinite(args.max_vpp) or not 0 < args.max_vpp <= 2.2:
        p.error('max-fy-volts >0 bis 4; max-vpp >0 bis 2.2')
    if max(args.voltages) > args.max_fy_volts or max(args.frequencies_mhz) > 60:
        p.error('FY-Stellwert über --max-fy-volts oder Frequenz über 60 MHz')
    for cli in (args.fy, args.sds):
        if not cli.is_file():
            p.error(f'CLI fehlt: {cli}')
    output = args.output or Path(f'cal_scope_{args.input}_{datetime.now():%Y%m%d_%H%M%S}.csv')
    if output.exists():
        p.error(f'Datei existiert bereits: {output}')
    base = f'http://{args.host}:8080'
    info = api(base, '/api/v1/info')
    if info.get('name') != 'hamlab':
        raise RuntimeError(f'Kein HamLab: {info}')
    selected = int(args.input[-1])
    fields = ['utc', 'firmware_version', 'rf_input', 'fy_frequency_hz', 'fy_volts_setting', 'sample',
              'scope_channel', 'scope_frequency_hz', 'scope_vpp', 'scope_vrms', 'sine_ratio',
              'reference_dbm_vpp', 'reference_dbm_rms', 'a0_voltage_v', 'a1_voltage_v',
              'a0_dbm', 'a1_dbm', 'selected_correction_db', 'quality', 'scope_status']
    print(f'HF direkt an {args.input.upper()}, Scope CH{args.scope_channel} parallel hochohmig; nur AD8307 terminiert mit 50 Ω.')
    print('Scope passend skalieren, mehrere Perioden erfassen. FY-Stellwert ist kein Referenzpegel.')
    started = False
    try:
        with output.open('x', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for mhz in args.frequencies_mhz:
                hz = round(mhz * 1e6)
                for setting in args.voltages:
                    started = True
                    run([args.fy, '-c', args.fy_channel, 'set', '--wave', 'sine', '--freq', hz,
                         '--volts', setting, '--offset', 0, '--on'])
                    time.sleep(args.settle)
                    for sample in range(1, args.samples + 1):
                        raw = run([args.sds, 'status'])
                        rms, vpp, freq = scope_read(raw, args.scope_channel)
                        if rms <= 0 or vpp <= 0 or vpp > args.max_vpp:
                            raise RuntimeError(f'Scope-Pegel ungültig oder > {args.max_vpp} Vpp: {vpp}, {rms}')
                        result = api(base, '/api/v1/measure')
                        if not result.get('measurement_valid') or len(result.get('channels', [])) != 2:
                            raise RuntimeError(f'Ungültige HamLab-Messung: {result}')
                        a0, a1 = result['channels']
                        ref = 10 * math.log10(vpp * vpp / (8 * args.resistance) * 1000)
                        ref_rms = 10 * math.log10(rms * rms / args.resistance * 1000)
                        ratio = vpp / (2 * math.sqrt(2) * rms)
                        flags = []
                        if abs(ratio - 1) > .1:
                            flags.append('rms_vpp_mismatch')
                        if abs(freq / hz - 1) > .02:
                            flags.append('frequency_mismatch')
                        correction = ref - result['channels'][selected]['dbm']
                        writer.writerow(dict(utc=datetime.now(timezone.utc).isoformat(), firmware_version=info.get('version'),
                            rf_input=args.input, fy_frequency_hz=hz, fy_volts_setting=setting, sample=sample,
                            scope_channel=args.scope_channel, scope_frequency_hz=freq, scope_vpp=vpp, scope_vrms=rms,
                            sine_ratio=ratio, reference_dbm_vpp=ref, reference_dbm_rms=ref_rms,
                            a0_voltage_v=a0['voltage_v'], a1_voltage_v=a1['voltage_v'], a0_dbm=a0['dbm'], a1_dbm=a1['dbm'],
                            selected_correction_db=correction, quality=','.join(flags) or 'plausible', scope_status=raw.strip()))
                        f.flush()
                        print(f'{mhz:g} MHz FY {setting:g} V: Scope {vpp:.4f} Vpp / {rms:.4f} Vrms; '
                              f'Offset {correction:+.3f} dB [{",".join(flags) or "plausible"}]', flush=True)
    finally:
        if started:
            try:
                run([args.fy, '-c', args.fy_channel, 'off'])
            except Exception as exc:
                print(f'FY manuell ausschalten! {exc}')
    print(f'CSV: {output}; keine Firmwareänderung. Nur plausible Punkte für den Abgleich verwenden.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        raise SystemExit(f'Abbruch: {exc}')
