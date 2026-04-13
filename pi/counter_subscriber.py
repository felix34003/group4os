import zenoh
import sys
import os
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_zenoh_config, register_signals

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    print("Connecting to Zenoh as Pi (Counter Sub)...")
    z_config = get_zenoh_config("connect")
    session = zenoh.open(z_config)

    status_file = "/tmp/felix_counter.txt"

    def counter_handler(sample):
        val = bytes(sample.payload).decode('utf-8')
        print(f"Received counter: {val}", flush=True)
        with open(status_file, "w") as f:
            f.write(val)

    def shutdown_handler(_sample):
        print("Shutdown command received.", flush=True)
        stop_event.set()

    subs = [
        session.declare_subscriber(config['topics']['counter'], counter_handler),
        session.declare_subscriber(config['topics']['shutdown'], shutdown_handler),
    ]

    print("Counter Subscriber started.", flush=True)
    stop_event.wait()
    del subs

    print("Stopping Pi Counter Subscriber...")
    session.close()

if __name__ == "__main__":
    main()
