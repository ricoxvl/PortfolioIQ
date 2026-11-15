#!/usr/bin/env python3
"""Optional external, nonblocking connectivity probe of the two official sources.

No credentials, no writes, no user data. Intended for a separate advisory CI job:
upstream outages never block production finance/security tests or cause bogus fallbacks.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'production'))
from server.official_feeds import (
    _download_fixed,ECB_SOURCE,MAX_ECB_BYTES,parse_ecb_csv,
    treasury_source_url,MAX_TREASURY_BYTES,parse_treasury_csv
)


def run():
    ok=True
    for name,url,max_bytes,parse in [
        ('European Central Bank EUR/USD',ECB_SOURCE,MAX_ECB_BYTES,parse_ecb_csv),
        ('U.S. Treasury nominal par yields',treasury_source_url(),MAX_TREASURY_BYTES,parse_treasury_csv),
    ]:
        try:
            rows=parse(_download_fixed(url,max_bytes=max_bytes))
            print(f'PASS: {name}: {len(rows)} published dated observations; newest={rows[-1]["date"]}; publisher={url.split("/")[2]}')
        except Exception as e:
            ok=False
            # Avoid logging request URL, headers, or any provider response body.
            print(f'UNAVAILABLE: {name}: official CSV not retrievable or validation failed ({type(e).__name__})')
    return 0 if ok else 1

if __name__=='__main__':sys.exit(run())