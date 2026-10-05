"""TLS downloads using the bundled Python OpenSSL runtime."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

STATE = Path(__file__).resolve().parent / 'logs' / 'ai-state.json'

def opened(url, proxy):
    opener = build_opener(ProxyHandler({'https': 'http://127.0.0.1:7897'} if proxy else {}))
    return opener.open(Request(url, headers={'User-Agent':'RedMap-LocalAI/1.1'}), timeout=30)

def main():
    _, mode, url, *args = sys.argv
    for attempt, proxy in enumerate((False, True, False), 1):
        try:
            with opened(url, proxy) as response:
                if mode == '--json':
                    sys.stdout.buffer.write(response.read())
                    return
                path, expected, size = args
                path = Path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                STATE.parent.mkdir(parents=True, exist_ok=True)
                part = path.with_suffix(path.suffix + '.part')
                size = int(size)
                digest = hashlib.sha256()
                count = 0
                last = 0
                with part.open('wb') as target:
                    while chunk := response.read(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        count += len(chunk)
                        if time.monotonic() - last > 0.5:
                            STATE.write_text(json.dumps({'phase':'download','message':f'{path.name}: {count/1048576:.1f} / {size/1048576:.1f} MB','percent':min(99,int(count*100/size)) if size else 0}), encoding='utf-8')
                            last = time.monotonic()
                if digest.hexdigest().lower() != expected.lower():
                    raise ValueError('SHA256 mismatch')
                os.replace(part, path)
                return
        except Exception as error:
            print(f'Attempt {attempt}: {error}', file=sys.stderr)
            if attempt == 3:
                raise

if __name__ == '__main__':
    main()
