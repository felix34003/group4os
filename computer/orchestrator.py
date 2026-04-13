import zenoh
import json
import time
import sys
import os
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_heartbeat, get_zenoh_config, register_signals

EXPECTED_NODES = {"Pi", "PC"}
STALE_THRESHOLD = 6.0  # seconds before a node is considered lost

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    print("=== FelixOS Orchestrator ===")
    z_config = get_zenoh_config("listen")
    session = zenoh.open(z_config)

    node_stats = {}
    ready_nodes = set()
    ready_event = threading.Event()

    def hb_handler(sample):
        try:
            hb = json.loads(bytes(sample.payload).decode('utf-8'))
            node = hb['node']
            node_stats[node] = hb
            if node in EXPECTED_NODES and node not in ready_nodes:
                ready_nodes.add(node)
                print(f"  [+] {node} is online.", flush=True)
                if EXPECTED_NODES.issubset(ready_nodes):
                    ready_event.set()
        except Exception:
            pass

    def shutdown_handler(_sample):
        # Another node requested shutdown — honour it
        stop_event.set()

    pub_shutdown = session.declare_publisher(config['topics']['shutdown'])
    pub_hb = session.declare_publisher(f"{config['topics']['heartbeat']}/orchestrator")

    subs = [
        session.declare_subscriber(f"{config['topics']['heartbeat']}/*", hb_handler),
        session.declare_subscriber(config['topics']['shutdown'], shutdown_handler),
    ]

    print(f"Waiting for nodes: {EXPECTED_NODES} ...", flush=True)
    if not ready_event.wait(timeout=15.0):
        missing = EXPECTED_NODES - ready_nodes
        print(f"  [!] Timeout waiting for: {missing}. Continuing anyway.", flush=True)
    else:
        print("All nodes online. System ready.", flush=True)

    last_hb_time = 0
    last_status_time = 0

    try:
        while not stop_event.is_set():
            now = time.time()

            # Publish own heartbeat every 2 s
            if now - last_hb_time > 2.0:
                pub_hb.put(json.dumps(get_heartbeat("Orchestrator")))
                last_hb_time = now

            # Print node status every 5 s
            if now - last_status_time > 5.0:
                print("\n--- Node Status ---", flush=True)
                for name, stats in node_stats.items():
                    age = now - stats.get('timestamp', now)
                    state = "OK" if age < STALE_THRESHOLD else "STALE"
                    print(f"  {name}: CPU {stats.get('cpu_percent','?')}%  "
                          f"MEM {stats.get('memory_percent','?')}%  [{state}]", flush=True)
                if not node_stats:
                    print("  (no nodes reporting)", flush=True)
                last_status_time = now

            stop_event.wait(1.0)

    except KeyboardInterrupt:
        stop_event.set()
    finally:
        print("\nBroadcasting shutdown to all nodes...", flush=True)
        pub_shutdown.put("shutdown")
        time.sleep(2.0)  # Give nodes time to receive and clean up
        del subs
        session.close()
        print("Orchestrator stopped.", flush=True)

if __name__ == "__main__":
    main()
