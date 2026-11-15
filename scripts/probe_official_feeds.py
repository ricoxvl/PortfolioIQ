#!/usr/bin/env python3
"""Advisory external source verification: no secrets, no writes, no synthetic data."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'production'))
from server.official_feeds import (
 fx_source_url,parse_frankfurter_ecb_json,MAX_FX_BYTES,
 treasury_source_url,parse_treasury_csv,MAX_TREASURY_BYTES,
 TREASURY_MIRROR,parse_treasury_mirror_csv,MAX_MIRROR_BYTES,_download_fixed
)

def run():
    okay=True
    configs=[
       ('ECB-only FX via Frankfurter',[(fx_source_url(),parse_frankfurter_ecb_json,MAX_FX_BYTES)]),
       ('U.S. Treasury nominal yields',[(treasury_source_url(),parse_treasury_csv,MAX_TREASURY_BYTES),
                                        (TREASURY_MIRROR,parse_treasury_mirror_csv,MAX_MIRROR_BYTES)]),
    ]
    for name,candidates in configs:
        success=False
        for url,parser,maximum in candidates:
            try:
                rows=parser(_download_fixed(url,max_bytes=maximum))
                print(f'PASS: {name}: {len(rows)} published observations, last {rows[-1]["date"]}; via {url.split("/")[2]}')
                success=True;break
            except Exception as exc:
                # All URLs are fixed, and only safe categorical messages are logged.
                print(f'Unavailable at {url.split("/")[2]}: {type(exc).__name__}: {str(exc)[:100]}')
        if not success:okay=False
    return 0 if okay else 1

if __name__=='__main__':sys.exit(run())