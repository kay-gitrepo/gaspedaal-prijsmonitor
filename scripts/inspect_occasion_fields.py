"""Toon de sleutelstructuur van advertenties uit een lokaal opgeslagen Gaspedaal-zoekpagina.

Gebruik: python scripts/inspect_occasion_fields.py pad/naar/zoekpagina.html [aantal]

Print van de eerste advertenties (standaard drie) alleen geneste sleutelnamen en waardetypen,
nooit de waarden zelf. Zo kan de structuur gedeeld worden zonder persoons- of dealergegevens.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.gaspedaal_site import _flight_occasions  # noqa: E402


def structure(value, prefix='', out=None):
    out = [] if out is None else out
    if isinstance(value, dict):
        for key in sorted(value):
            structure(value[key], f'{prefix}.{key}' if prefix else key, out)
    elif isinstance(value, list):
        kinds = sorted({type(v).__name__ for v in value}) or ['leeg']
        out.append(f'{prefix}[]  ({", ".join(kinds)}, {len(value)} items)')
        for item in value[:1]:
            if isinstance(item, (dict, list)):
                structure(item, prefix + '[]', out)
    else:
        out.append(f'{prefix}  ({type(value).__name__})')
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    raw = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    occasions = [o for o in _flight_occasions(raw) if isinstance(o, dict)]
    print(f'{len(occasions)} advertenties gevonden in de Next.js-stream')
    for i, occasion in enumerate(occasions[:count], 1):
        print(f'\n--- advertentie {i} ---')
        print('\n'.join(structure(occasion)))


if __name__ == '__main__':
    main()
