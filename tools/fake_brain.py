"""Stand-in for the webcam brain: POSTs finger counts to the backend.

  python tools/fake_brain.py              # type counts by hand (0-5, s = toggle SOS)
  python tools/fake_brain.py --auto       # cycle 0..5 then stop (tests the stale rule)
"""

import argparse
import itertools
import time

import requests


HEADERS: dict = {}


def post(url: str, payload: dict) -> None:
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=5)
        print(f"POST {payload} -> {r.status_code} {r.text}")
    except requests.RequestException as e:
        print(f"backend unreachable: {e}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/fingers")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--key", default="", help="API key if the backend has API_KEY set")
    args = p.parse_args()
    if args.key:
        HEADERS["X-API-Key"] = args.key

    if args.auto:
        for count in itertools.chain(range(6), range(4, -1, -1)):
            post(args.url, {"count": count, "brightness": count * 51})
            time.sleep(1)
        print("Brain going silent. The fake ESP32 should go dark within 3 s.")
        return

    sos = False
    print("Enter 0-5 to set the count, 's' to toggle SOS, 'q' to quit.")
    print("Note: counts go stale after 3 s, like a real camera that stopped reporting.")
    while (line := input("> ").strip().lower()) != "q":
        if line == "s":
            sos = not sos
            post(args.url, {"count": 0, "sos": sos})
        elif line.lstrip("-").isdigit():
            post(args.url, {"count": int(line), "brightness": min(int(line) * 51, 255)})
        else:
            print("?")


if __name__ == "__main__":
    main()
