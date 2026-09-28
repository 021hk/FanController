"""
test_esp.py - Connectivity smoke test for the ESP8266 fan controller.
"""

from __future__ import annotations
import argparse
import time
import requests
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.4.1")
    p.add_argument("--port", type=int, default=80)
    args = p.parse_args()
    base = f"http://{args.ip}:{args.port}"

    print(f"[*] GET {base}/status")
    try:
        r = requests.get(f"{base}/status", timeout=3)
        r.raise_for_status()
        s = r.json()
        print(f"    CPU temp={s.get('cpu_temp')}C  fan={s.get('cpu_pct')}%  mode={s.get('cpu_mode')}")
        print(f"    GPU temp={s.get('gpu_temp')}C  fan={s.get('gpu_pct')}%  mode={s.get('gpu_mode')}")
        print(f"    profile={s.get('profile')}  game={s.get('game')}  wifi={s.get('wifi')}")
    except Exception as e:
        print(f"[!] HTTP request failed: {e}")
        print("    Make sure ESP8266 is powered, flashed, on same WiFi, and IP is correct.")
        sys.exit(1)

    print()
    print("[*] Forcing CPU fan to 100% for 3 seconds...")
    requests.get(f"{base}/set?fan=cpu&percent=100&mode=manual")
    time.sleep(3)

    print("[*] Forcing GPU fan to 100% for 3 seconds...")
    requests.get(f"{base}/set?fan=gpu&percent=100&mode=manual")
    time.sleep(3)

    print("[*] Resetting both to Auto...")
    requests.get(f"{base}/set?fan=cpu&percent=0&mode=auto")
    requests.get(f"{base}/set?fan=gpu&percent=0&mode=auto")

    print()
    print("[OK] Test complete. Listen to your fans!")
    print("    If you heard them ramp up then drop back, the controller works.")


if __name__ == "__main__":
    main()
