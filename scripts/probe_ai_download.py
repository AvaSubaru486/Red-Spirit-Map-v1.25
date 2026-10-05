"""Check available model metadata transports without downloading weights."""
import concurrent.futures
import json
import sys
from urllib.request import build_opener, ProxyHandler, Request

def probe(url):
    try:
        with build_opener(ProxyHandler({})).open(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
            if 'releases/download' in url:
                print(url, response.status, response.read(16).hex(), flush=True)
                return
            data = json.load(response)
            if 'Data' in data:
                print(url, [f for f in data['Data']['Files'] if 'q4_k_m' in f['Name'].lower()], flush=True)
            else:
                print(url, data['sha'], [f for f in data['siblings'] if 'q4_k_m' in f['rfilename'].lower()], flush=True)
    except Exception as error:
        print(url, type(error).__name__, str(error), flush=True)

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor() as executor:
        list(executor.map(probe, sys.argv[1:] or [
            'https://hf-mirror.com/api/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF?blobs=true',
            'https://modelscope.cn/api/v1/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/repo/files?Revision=master&Recursive=true',
        ]))
