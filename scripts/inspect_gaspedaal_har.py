#!/usr/bin/env python3
"""Inspect a locally exported Chrome HAR for JSON search endpoints.

Prints only request path, query parameter *names* and JSON container shape.
Never prints cookie, authorization, URL query values or response contents.
Do not commit or share the HAR: it can contain session secrets.
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

HOSTS={'api.gaspedaal.nl','www.gaspedaal.nl','gaspedaal.nl'}


def arrays(value, prefix='', max_depth=5):
    if max_depth <= 0: return []
    if isinstance(value,list): return [(prefix or '@',len(value))]
    if isinstance(value,dict):
        output=[]
        for k,v in list(value.items())[:40]:
            if isinstance(v,(dict,list)):
                output.extend(arrays(v,f'{prefix}.{k}' if prefix else k,max_depth-1))
        return output
    return []


def inspect(data):
    for entry in data.get('log',{}).get('entries',[]):
        request=entry.get('request',{})
        u=urlsplit(request.get('url',''))
        if u.hostname not in HOSTS: continue
        response=entry.get('response',{})
        mime=response.get('content',{}).get('mimeType','').lower()
        if not any(x in mime for x in ('json','javascript')): continue
        parsed=None
        content=response.get('content',{}).get('text')
        if content and response.get('content',{}).get('encoding') != 'base64':
            try:parsed=json.loads(content)
            except (ValueError,TypeError):pass
        paths=arrays(parsed) if parsed is not None else []
        # Do not disclose query values or cookies even if embedded in a HAR.
        print(f'{request.get("method","GET")} {u.hostname}{u.path} HTTP {response.get("status","?")}')
        print(f'  query keys: {", ".join(sorted({k for k,v in parse_qsl(u.query)})) or "—"}')
        print(f'  JSON arrays: {paths[:12] if paths else "unknown (HAR lacks readable response)"}')
        if isinstance(parsed,dict):
            print(f'  JSON top-level keys: {", ".join(list(parsed.keys())[:30])}')


def main():
    if len(sys.argv)!=2:
        raise SystemExit('Gebruik: python scripts/inspect_gaspedaal_har.py netwerk.har')
    inspect(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))

if __name__=='__main__': main()
