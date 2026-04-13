import zenoh
import json
import time
import sys
import os
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from utils import load_config, get_heartbeat, get_zenoh_config, register_signals

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    print("Connecting to Zenoh as PC (Counter Pub)...")
    z_config = get_zenoh_config("listen")
    session = zenoh.open(z_config)

    pub_counter = session.declare_publisher(config['topics']['counter'])
    pub_hb = session.declare_publisher(f"{config['topics']['heartbeat']}/pc")

    def shutdown_handler(_sample):
        print("Shutdown command received.", flush=True)
        stop_event.set()

    sub_shutdown = session.declare_subscriber(config['topics']['shutdown'], shutdown_handler)

    counter = 0
    rate = config['config']['counter_rate_hz']
    interval = 1.0 / rate

    print(f"Counter Publisher started. Sending to '{config['topics']['counter']}' at {rate}Hz...")

    try:
        while not stop_event.is_set():
            pub_counter.put(str(counter))
            print(f"Sent counter: {counter}")
            counter += 1

            if int(time.time()) % 2 == 0:
                hb = get_heartbeat("PC")
                pub_hb.put(json.dumps(hb))

            stop_event.wait(interval)
    finally:
        del sub_shutdown
        session.close()
        print("PC Counter Publisher stopped.")

if __name__ == "__main__":
    main()
