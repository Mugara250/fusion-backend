"""Stand-in for the ESP32 body: polls GET /fingers 5x/second and 'lights' LEDs.

Parses the response the same way the C++ sketch on slide 13 does
(find "count": and read the number after it), so if this works the chip will too.

  python tools/fake_esp32.py --url http://<laptop-ip>:8000/fingers
"""

import argparse
import time

import requests

LED_PINS = [23, 22, 21, 19, 18]


def parse_count(body: str) -> int:
    at = body.find('"count":')
    digits = ""
    for ch in body[at + 8:]:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits or 0)  # Arduino's toInt() returns 0 on garbage


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/fingers")
    args = p.parse_args()

    shown = -1
    while True:
        try:
            r = requests.get(args.url, timeout=5)
            code = r.status_code
        except requests.RequestException:
            code = -1  # what HTTPClient returns when no house is found

        if code == 200:
            count = parse_count(r.text)
            if count != shown:
                leds = "".join("●" if i < count else "○" for i in range(len(LED_PINS)))
                tick = " *tick*" if count > shown else ""
                print(f"fingers = {count}  {leds}{tick}   {r.text}")
                shown = count
        else:
            print(f"backend error {code}")
        time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
