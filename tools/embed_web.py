#!/usr/bin/env python3
"""Embed web/hamlab.html as a C string for the Pico HTTP server."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = ROOT / 'src' / 'hamlab_web.h'
with target.open('w', encoding='ascii') as out:
    out.write('/* Generated from web/hamlab.html and web/sweep.js. */\n')
    out.write('#ifndef HAMLAB_WEB_H_\n#define HAMLAB_WEB_H_\n')
    for name, source in (('html', ROOT / 'web' / 'hamlab.html'),
                         ('sweep_js', ROOT / 'web' / 'sweep.js'),
                         ('compact_html', ROOT / 'web' / 'compact.html')):
        out.write(f'static const char {name}[] =\n')
        for line in source.read_text(encoding='utf-8').splitlines(keepends=True):
            out.write(json.dumps(line, ensure_ascii=True) + '\n')
        out.write(';\n')
    out.write('#endif\n')
print(f'Generated {target}')
