#!/usr/bin/env python3
"""FY6900 antenna SWR sweep; scalar open normalization, no vector correction."""
import argparse, bisect, csv, datetime, json, math, subprocess, sys
from pathlib import Path
from measure_swr import load


def interpolate(points, hz, forward):
    frequencies = sorted(points)
    if not frequencies[0] <= hz <= frequencies[-1]:
        raise ValueError('Sweep liegt außerhalb der Referenz')
    i = bisect.bisect_left(frequencies, hz)
    def delta(f):
        return points[f][1-forward] - points[f][forward]
    if frequencies[i] == hz:
        return delta(hz)
    lo, hi = frequencies[i-1], frequencies[i]
    return delta(lo)+(delta(hi)-delta(lo))*(hz-lo)/(hi-lo)


def main():
    p = argparse.ArgumentParser(description='Antennen-SWR und Minimum mit FY6900/HamLab')
    p.add_argument('--host', default='192.168.178.69')
    p.add_argument('--fy', default='/home/ulrich/Dokumente/GitHub/workbench/cmd/fy')
    p.add_argument('--open', type=Path, default=Path('selbstbau_offen_1-30mhz_umbau1.csv'))
    p.add_argument('--load', type=Path, default=Path('selbstbau_50ohm_1-30mhz_umbau1.csv'))
    p.add_argument('--forward', choices=['a0','a1'], default='a1')
    p.add_argument('--start-mhz', type=float, default=6.9)
    p.add_argument('--stop-mhz', type=float, default=7.1)
    p.add_argument('--step-mhz', type=float, default=0.005)
    p.add_argument('--samples', type=int, default=2)
    p.add_argument('--output', type=Path)
    p.add_argument('--raw', type=Path, help='Vorhandenen Sweep auswerten statt messen')
    p.add_argument('--interactive', action='store_true')
    p.add_argument('--no-plot', action='store_true')
    a = p.parse_args()
    if not all(math.isfinite(x) for x in [a.start_mhz,a.stop_mhz,a.step_mhz]) or not 0<a.start_mhz<a.stop_mhz or a.step_mhz<=0 or a.samples<1:
        p.error('Ungültige Sweep-Parameter')
    o, settings = load(a.open); l, ls = load(a.load)
    if settings != ls: raise ValueError('Referenzen haben unterschiedliche Generatoreinstellungen')
    fw = int(a.forward[-1])
    for hz in [round(a.start_mhz*1e6),round(a.stop_mhz*1e6)]:
        interpolate(o,hz,fw); interpolate(l,hz,fw)
    out = a.output or Path('antenne_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.csv')
    raw = a.raw or out.with_name(out.stem+'_raw.csv')
    if out.exists() or (not a.raw and raw.exists()): raise ValueError('Ausgabedatei existiert bereits')
    print('Referenzen werden zwischen ihren Frequenzpunkten linear in dB interpoliert.')
    if not a.raw:
        ch, volts, att = settings
        subprocess.run([sys.executable,str(Path(__file__).with_name('sweep_fy6900.py')),
            '--host',a.host,'--fy',a.fy,'--channel',ch,'--volts',volts,'--attenuation',att,
            '--start-mhz',str(a.start_mhz),'--stop-mhz',str(a.stop_mhz),'--step-mhz',str(a.step_mhz),
            '--samples',str(a.samples),'--output',str(raw),'--no-plot'],check=True)
    d, ds = load(raw)
    if ds != settings: raise ValueError('Messung passt nicht zu Referenzeinstellungen')
    rows=[]
    for hz,v in sorted(d.items()):
        od=interpolate(o,hz,fw)
        rl=od-(v[1-fw]-v[fw])
        limit=od-interpolate(l,hz,fw)
        flag='invalid' if rl<=0 else 'near_limit' if rl>=limit-3 else 'ok'
        gamma=10**(-rl/20) if rl>0 else 1
        swr=(1+gamma)/(1-gamma) if rl>0 else None
        rows.append([hz,rl,swr,limit,flag,v[0],v[1]])
    with out.open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['frequency_hz','return_loss_db','swr','reference_limit_db','quality','a0_dbm','a1_dbm']);w.writerows(rows)
    valid=[r for r in rows if r[2] is not None]
    if valid:
        best=min(valid,key=lambda r:r[2]);print(f'Minimum im gemessenen Raster: {best[0]/1e6:.6f} MHz, SWR {best[2]:.3f}, RL {best[1]:.2f} dB ({best[4]})')
        if best is rows[0] or best is rows[-1]: print('Minimum liegt am Sweep-Rand: Frequenzbereich erweitern.')
        if best[4]=='near_limit': print('Minimum nahe der Referenzgrenze: SWR-Zahl nur als Orientierung verwenden.')
    else: print('Keine gültigen SWR-Werte.')
    print(f'CSV: {out}; Rohdaten: {raw}')
    if not a.no_plot:
        q=lambda x:json.dumps(str(x))
        script='set datafile separator comma\nset grid\nset xlabel "Frequenz (MHz)"\nset ylabel "SWR"\nset yrange [1:*]\n'
        plot=f'plot {q(out)} using ($1/1e6):3 with linespoints title "Antenne", 2 with lines dt 2 title "SWR 2"\n'
        script+='set terminal pngcairo size 1100,650\nset output '+q(out.with_suffix('.png'))+'\n'+plot
        if a.interactive:script+='unset output\nset terminal qt\n'+plot
        subprocess.run(['gnuplot']+(['-persist'] if a.interactive else []),input=script,text=True,check=True)

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,subprocess.CalledProcessError) as e: sys.exit(f'Abbruch: {e}')
