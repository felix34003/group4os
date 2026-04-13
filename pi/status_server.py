import http.server
import socketserver
import json
import zenoh
import sys
import os
import threading

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_zenoh_config, register_signals

node_stats = {}
last_counter = "0"

def main():
    global last_counter
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    z_config = get_zenoh_config("connect")
    session = zenoh.open(z_config)

    def hb_handler(sample):
        try:
            hb = json.loads(bytes(sample.payload).decode('utf-8'))
            node_stats[hb['node']] = hb
        except Exception:
            pass

    def counter_handler(sample):
        global last_counter
        last_counter = bytes(sample.payload).decode('utf-8')

    def shutdown_handler(_sample):
        print("Shutdown command received.", flush=True)
        stop_event.set()

    subs = [
        session.declare_subscriber(f"{config['topics']['heartbeat']}/*", hb_handler),
        session.declare_subscriber(config['topics']['counter'], counter_handler),
        session.declare_subscriber(config['topics']['shutdown'], shutdown_handler),
    ]

    class StatusHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            response = "=== FelixOS Network Status ===\n\n"
            response += f"Live Counter: {last_counter}\n\n"
            response += "Active Nodes:\n"
            for node, stats in node_stats.items():
                response += f"- {node}: {stats['status']} (CPU: {stats['cpu_percent']}%, MEM: {stats['memory_percent']}%)\n"
            self.wfile.write(response.encode())

        def log_message(self, _format, *_args):
            pass  # Suppress request logs

    PORT = 8000
    # Use timeout so handle_request() returns periodically and we can check stop_event
    httpd = socketserver.TCPServer(("", PORT), StatusHandler)
    httpd.timeout = 1.0

    def serve():
        while not stop_event.is_set():
            httpd.handle_request()

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()

    print(f"Status Server running at http://localhost:{PORT}", flush=True)
    stop_event.wait()

    print("Stopping Pi Status Server...")
    del subs
    httpd.server_close()
    session.close()

if __name__ == "__main__":
    main()
