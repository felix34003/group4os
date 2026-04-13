import zenoh
import cv2
import numpy as np
import json
import sys
import os
import threading
import av

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_zenoh_config, register_signals

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    print("--- NATIVE MISSION CONTROL (H.264 OSD) ---")
    print("Connecting to Zenoh...")
    z_config = get_zenoh_config("listen")
    session = zenoh.open(z_config)

    node_stats = {}
    codec = av.CodecContext.create('h264', 'r')

    # Shared frame buffer — written by Zenoh callback, read by main thread
    latest_frame = [None]
    frame_lock = threading.Lock()

    def heartbeat_handler(sample):
        try:
            hb = json.loads(bytes(sample.payload).decode('utf-8'))
            node_stats[hb['node']] = hb
        except Exception:
            pass

    def video_handler(sample):
        try:
            packets = codec.parse(bytes(sample.payload))
            for packet in packets:
                frames = codec.decode(packet)
                for frame in frames:
                    img = frame.to_ndarray(format='bgr24')

                    # Draw OSD overlay
                    overlay = img.copy()
                    cv2.rectangle(overlay, (5, 5), (315, 80), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)
                    cv2.putText(img, "FELIX MISSION CONTROL [H.264]", (10, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                    y = 40
                    for node, stats in node_stats.items():
                        temp = stats.get('temp', '--')
                        cpu = stats.get('cpu_percent', '--')
                        last_c = stats.get('last_counter', '0')
                        temp_str = f"| {temp}C" if temp not in (0.0, '--') else ""
                        cv2.putText(img, f"{node}: {cpu}% CPU {temp_str}", (10, y),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                        cv2.putText(img, f"STEP: {last_c}", (10, y + 15),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                        y += 35

                    with frame_lock:
                        latest_frame[0] = img
        except Exception:
            pass

    def shutdown_handler(_sample):
        print("Shutdown command received.", flush=True)
        stop_event.set()

    subs = [
        session.declare_subscriber(config['topics']['video'], video_handler),
        session.declare_subscriber(f"{config['topics']['heartbeat']}/*", heartbeat_handler),
        session.declare_subscriber(config['topics']['shutdown'], shutdown_handler),
    ]

    print("Go Crazy OSD Active. Press ESC in video window to exit.")

    # cv2 GUI must run on the main thread
    while not stop_event.is_set():
        with frame_lock:
            frame = latest_frame[0]

        if frame is not None:
            cv2.imshow("FelixOS Live", frame)

        key = cv2.waitKey(30)
        if key & 0xFF == 27:  # ESC
            stop_event.set()

    cv2.destroyAllWindows()
    del subs
    session.close()

if __name__ == "__main__":
    main()
