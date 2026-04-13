import zenoh
import json
import time
import sys
import os
import subprocess
import threading
import select

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_heartbeat, get_zenoh_config, register_signals

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    pi_ip = config['nodes']['pi']['ip']
    print(f"Connecting to Zenoh as Pi ({pi_ip})...")
    z_config = get_zenoh_config("connect")
    session = zenoh.open(z_config)

    pub_video = session.declare_publisher(
        config['topics']['video'],
        reliability=zenoh.Reliability.BEST_EFFORT,
        congestion_control=zenoh.CongestionControl.DROP
    )
    pub_hb = session.declare_publisher(f"{config['topics']['heartbeat']}/pi")

    def shutdown_handler(_sample):
        print("Shutdown command received.", flush=True)
        stop_event.set()

    sub_shutdown = session.declare_subscriber(config['topics']['shutdown'], shutdown_handler)

    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-f", "v4l2",
        "-video_size", "640x480",
        "-framerate", str(config['config']['video_fps']),
        "-i", "/dev/video0",
        "-c:v", "h264_v4l2m2m",
        "-b:v", "2M",
        "-g", str(config['config']['video_fps']),
        "-f", "h264",
        "-"
    ]

    print("Launching Hardware H.264 Encoder...", flush=True)
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=0)

    last_hb_time = 0
    status_file = os.path.join(os.path.dirname(__file__), "..", "felix_counter.txt")
    buffer_size = 4096

    print("Go Crazy Vision active. Sending Hardware H.264 to Zenoh...", flush=True)

    try:
        while not stop_event.is_set():
            # 1-second timeout so we can check stop_event even if ffmpeg stalls
            ready, _, _ = select.select([process.stdout], [], [], 1.0)
            if not ready:
                continue

            data = process.stdout.read(buffer_size)
            if not data:
                print("FFmpeg pipe closed.", flush=True)
                break

            pub_video.put(data)

            now = time.time()
            if now - last_hb_time > 2.0:
                last_counter = 0
                try:
                    if os.path.exists(status_file):
                        with open(status_file, "r") as f:
                            last_counter = int(f.read().strip())
                except Exception:
                    pass
                hb = get_heartbeat("Pi", last_counter=last_counter)
                pub_hb.put(json.dumps(hb))
                last_hb_time = now
    finally:
        del sub_shutdown
        process.terminate()
        session.close()
        print("Pi Video Publisher stopped.", flush=True)

if __name__ == "__main__":
    main()
