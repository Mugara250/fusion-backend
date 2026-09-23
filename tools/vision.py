"""The brain: webcam -> MediaPipe -> finger count -> POST to the backend.

Run on Windows (WSL cannot see the webcam) with Python 3.10-3.12:
  python vision.py                                   # backend on this laptop
  python vision.py --url http://<ip>:8000/fingers    # backend elsewhere
  python vision.py --url https://<app>.onrender.com/fingers --key <API_KEY>   # hosted

Posts every 0.1 s (not only on change) so a steady hand does not trip the
backend's 3-second stale rule. Press Q in the window to quit.
"""

import argparse
import math
import sys
import time

import cv2
import mediapipe as mp
import requests

FINGERS = [(4, 3), (8, 6), (12, 10), (16, 14), (20, 18)]  # (tip, middle joint)


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/fingers")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--key", default="", help="API key if the backend has API_KEY set")
    args = p.parse_args()

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
    last_sent = 0.0
    sos = False
    peace_started = None
    peace_latched = False
    online = True
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
            count, brightness, peace = 0, 0, False

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                pts = hand.landmark
                wrist = pts[0]

                # A finger is up when its tip is farther from the wrist than its middle joint.
                up = [distance(pts[t], wrist) > distance(pts[m], wrist) for t, m in FINGERS]
                count = sum(up)
                peace = up[1] and up[2] and not up[3] and not up[4]

                # Pinch: thumb-to-index distance relative to hand size -> 0..255.
                pinch = distance(pts[4], pts[8]) / max(distance(pts[0], pts[9]), 0.001)
                brightness = int(255 * max(0, min(1, (pinch - 0.15) / 0.85)))

                drawing.draw_landmarks(frame, hand, hands_api.HAND_CONNECTIONS)

            # Hold peace for 1 s to toggle SOS; release before toggling again.
            if peace:
                peace_started = peace_started or now
                if not peace_latched and now - peace_started >= 1.0:
                    sos, peace_latched = not sos, True
            else:
                peace_started, peace_latched = None, False

            if now - last_sent >= 0.1:
                try:
                    requests.post(
                        args.url,
                        json={"count": count, "brightness": brightness, "sos": sos},
                        headers={"X-API-Key": args.key} if args.key else {},
                        timeout=3,
                    ).raise_for_status()
                    online = True
                except requests.RequestException:
                    if online:
                        print("Backend unavailable at", args.url, "- is uvicorn running?")
                    online = False
                last_sent = now

            cv2.putText(frame, f"Fingers: {count}  Brightness: {brightness}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, "SOS ON" if sos else "SOS OFF", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255) if sos else (255, 255, 255), 2)
            if not online:
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

    camera.release()
    cv2.destroyAllWindows()
    print("Stopped.")


if __name__ == "__main__":
    main()
