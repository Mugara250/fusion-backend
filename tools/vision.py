"""The brain: webcam -> MediaPipe -> finger count -> POST to the backend.

Run on Windows (WSL cannot see the webcam) with Python 3.10-3.12:
  python vision.py                                   # backend on this laptop
  python vision.py --url http://<ip>:8000/fingers    # backend elsewhere
  python vision.py --url https://<app>.onrender.com/fingers --key <API_KEY>   # hosted

Sending happens on a background thread, so a slow network (hosted backend)
never freezes the video. It sends when the value changes, and at least once a
second anyway so a steady hand does not trip the backend's 3-second stale rule.
Press Q in the window to quit.
"""

import argparse
import math
import sys
import threading
import time

import cv2
import mediapipe as mp
import requests

FINGERS = [(8, 6), (12, 10), (16, 14), (20, 18)]  # index..little: (tip, middle joint)

# The thumb bends sideways, so the wrist rule always calls it "up". Instead: the
# thumb is up when its tip is clearly farther from the little finger's base (17)
# than the thumb's own base (2) is. Raise this if a folded thumb still counts,
# lower it if an open thumb is missed.
THUMB_RATIO = 1.2

SOS_HOLD = 2.0  # seconds to hold the rock sign to switch SOS on/off


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


class Sender:
    """Posts the latest reading on a background thread; the camera loop never waits."""

    HEARTBEAT = 1.0  # resend an unchanged value this often (stale rule is 3 s)

    def __init__(self, url, key):
        self.url = url
        self.session = requests.Session()  # keeps the HTTPS connection open between posts
        if key:
            self.session.headers["X-API-Key"] = key
        self.latest = None
        self.online = True
        self.wake = threading.Event()
        self.stopped = False
        threading.Thread(target=self._run, daemon=True).start()

    def update(self, payload):
        if payload != self.latest:
            self.latest = payload
            self.wake.set()  # send a change right away

    def stop(self):
        self.stopped = True
        self.wake.set()

    def _run(self):
        sent = None
        while not self.stopped:
            self.wake.wait(timeout=self.HEARTBEAT)
            self.wake.clear()
            payload = self.latest
            if payload is None or self.stopped:
                continue
            try:
                self.session.post(self.url, json=payload, timeout=5).raise_for_status()
                if not self.online:
                    print("Backend reachable again.")
                self.online = True
                sent = payload
            except requests.HTTPError as e:
                if self.online:
                    code = e.response.status_code
                    hint = {401: "wrong or missing --key", 404: "wrong URL path",
                            422: "bad data"}.get(code, "")
                    print(f"Backend refused the count: HTTP {code} {hint}")
                self.online = False
            except requests.RequestException:
                if self.online:
                    print("Backend unavailable at", self.url,
                          "- is it running? (a sleeping free server takes ~1 min)")
                self.online = False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/fingers")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--key", default="", help="API key if the backend has API_KEY set")
    args = p.parse_args()
    if not args.url.rstrip("/").endswith("/fingers"):
        args.url = args.url.rstrip("/") + "/fingers"

    # On Windows the default camera backend (MSMF) often stalls; DirectShow is reliable.
    if sys.platform == "win32":
        camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    else:
        camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        print("Cannot open webcam. Close other camera apps (Teams, Zoom, Camera) or try --camera 1.")
        return
    print("Camera opened. Sending to", args.url)

    hands_api = mp.solutions.hands
    drawing = mp.solutions.drawing_utils
    sender = Sender(args.url, args.key)
    sos = False
    rock_started = None
    rock_latched = False
    failed_reads = 0
    window = "Brain - press Q to quit"
    first_frame = True

    with hands_api.Hands(max_num_hands=1, min_detection_confidence=0.6) as detector:
        while True:
            ok, frame = camera.read()
            if not ok:
                failed_reads += 1
                if failed_reads == 1:
                    print("Camera gave no image, retrying...")
                if failed_reads > 100:
                    print("Camera never sent an image. Check Windows Settings > Privacy > Camera "
                          "(allow desktop apps), close other camera apps, or try --camera 1.")
                    break
                time.sleep(0.05)
                continue
            failed_reads = 0
            frame = cv2.flip(frame, 1)
            result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            now = time.monotonic()
            count, brightness, rock = 0, 0, False
            up = [False] * 5

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                pts = hand.landmark
                wrist = pts[0]

                # A finger is up when its tip is farther from the wrist than its middle joint.
                thumb_up = distance(pts[4], pts[17]) > THUMB_RATIO * distance(pts[2], pts[17])
                up = [thumb_up] + [distance(pts[t], wrist) > distance(pts[m], wrist)
                                   for t, m in FINGERS]
                count = sum(up)
                # Rock sign: index + little up, middle + ring down (thumb ignored).
                # Not peace: two fingers (index + middle) is a normal count of 2.
                rock = up[1] and up[4] and not up[2] and not up[3]

                # Pinch: thumb-to-index distance relative to hand size -> 0..255.
                pinch = distance(pts[4], pts[8]) / max(distance(pts[0], pts[9]), 0.001)
                brightness = int(255 * max(0, min(1, (pinch - 0.15) / 0.85)))

                drawing.draw_landmarks(frame, hand, hands_api.HAND_CONNECTIONS)

            # Hold the rock sign for SOS_HOLD seconds to toggle SOS; release before toggling again.
            if rock:
                rock_started = rock_started or now
                if not rock_latched and now - rock_started >= SOS_HOLD:
                    sos, rock_latched = not sos, True
                    print("SOS", "ON" if sos else "OFF")
            else:
                rock_started, rock_latched = None, False

            sender.update({"count": count, "brightness": brightness, "sos": sos})

            cv2.putText(frame, f"Fingers: {count}  Brightness: {brightness}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            fingers_text = " ".join(n if u else "-" for n, u in zip("TIMRL", up))
            cv2.putText(frame, f"Up: {fingers_text}", (20, 145),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            sos_text = "SOS ON - hold rock sign 2 s to turn off" if sos else "SOS OFF"
            if rock and not rock_latched:
                sos_text += f"  (hold... {now - rock_started:.1f}s)"
            cv2.putText(frame, sos_text, (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255) if sos else (255, 255, 255), 2)
            if not sender.online:
                cv2.putText(frame, "Backend unavailable", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow(window, frame)
            if first_frame:
                # Bring the window to the front so it does not hide behind VS Code.
                cv2.setWindowProperty(window, cv2.WND_PROP_TOPMOST, 1)
                print("Window open. Press Q in the window to quit.")
                first_frame = False
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    sender.stop()
    camera.release()
    cv2.destroyAllWindows()
    print("Stopped.")


if __name__ == "__main__":
    main()
