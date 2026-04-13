import os
import sys
import psutil
import subprocess
import time
from fabric import Connection
from utils import load_config

LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

# Files synced to the Pi on every startup
PI_SYNC_FILES = [
    ("pi/video_publisher.py",    "pi/video_publisher.py"),
    ("pi/counter_subscriber.py", "pi/counter_subscriber.py"),
    ("pi/status_server.py",      "pi/status_server.py"),
    ("pi/arduino_bridge.py",     "pi/arduino_bridge.py"),
    ("utils.py",                 "utils.py"),
    ("config.json",              "config.json"),
]


def identify_running_processes():
    current_pid = os.getpid()
    target_scripts = ['viedeo_receiver_osd.py', 'counter_publisher.py',
                      'orchestrator.py', 'start_all.py']
    print("Checking for existing group4os processes on PC...")
    found_any = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmd_str = " ".join(proc.info['cmdline'] or [])
                if any(s in cmd_str for s in target_scripts):
                    if proc.info['pid'] != current_pid:
                        print(f"  [Active] {cmd_str} (PID: {proc.info['pid']})")
                        found_any = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not found_any:
        print("  No other group4os processes found.")


def sync_code(conn, pi_cfg):
    """Push latest local files to the Pi before starting any nodes."""
    pi_proj_dir = f"/home/{pi_cfg['user']}/group4os"
    conn.run(f"mkdir -p {pi_proj_dir}/pi", timeout=10)
    print("Syncing code to Pi...")
    for local_rel, remote_rel in PI_SYNC_FILES:
        local_path  = os.path.join(LOCAL_ROOT, local_rel)
        remote_path = f"{pi_proj_dir}/{remote_rel}"
        conn.put(local_path, remote_path)
        print(f"  -> {remote_rel}")
    print("Code sync complete.")


def main():
    config = load_config()
    pi_cfg = config['nodes']['pi']

    print("=== group4os One-Click Startup ===")
    identify_running_processes()

    # 1. Ping check
    print(f"\nPinging Pi at {pi_cfg['ip']}...")
    ping_cmd = ["ping", "-n", "1", "-w", "2000", pi_cfg['ip']]
    if subprocess.call(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("Error: Pi is unreachable. Verify Tailscale is active.")
        return
    print("Pi is online!")

    # 2. SSH connect
    print(f"\nConnecting to Pi ({pi_cfg['ip']})...")
    conn = Connection(
        host=pi_cfg['ip'],
        user=pi_cfg['user'],
        connect_kwargs={"password": pi_cfg['ssh_pass']}
    )

    # 3. Kill any old group4os processes on the Pi
    print("Killing old Pi processes...")
    conn.run("pkill -u ece_441 python3 || true", timeout=10, warn=True)
    time.sleep(0.5)

    # 4. Sync code — Pi will always run the same version as the PC
    sync_code(conn, pi_cfg)

    # 5. Start Pi nodes in the background
    pi_proj_dir = f"/home/{pi_cfg['user']}/group4os"
    pi_nodes = [
        "pi/video_publisher.py",
        "pi/counter_subscriber.py",
        "pi/status_server.py",
        "pi/arduino_bridge.py",
    ]
    print("\nStarting Pi nodes...")
    for script in pi_nodes:
        cmd = (f"nohup {pi_cfg['venv']} {pi_proj_dir}/{script} "
               f">> {pi_proj_dir}/pi_nodes.log 2>&1 &")
        conn.run(cmd, disown=True)
        print(f"  Launched {script}")
    print("Pi nodes launched.")

    # 6. Start PC nodes as subprocesses
    print("\nLaunching PC nodes...")
    pc_procs = [
        subprocess.Popen([sys.executable,
                          os.path.join(LOCAL_ROOT, "computer/topics/counter_publisher.py")]),
        subprocess.Popen([sys.executable,
                          os.path.join(LOCAL_ROOT, "computer/website/dashboard_server.py")]),
    ]

    # 7. Run the orchestrator in the foreground — it owns the shutdown lifecycle
    print("Starting Orchestrator (Ctrl+C to shut everything down)...\n")
    orchestrator = subprocess.Popen(
        [sys.executable, os.path.join(LOCAL_ROOT, "computer/orchestrator.py")]
    )

    try:
        orchestrator.wait()
    except KeyboardInterrupt:
        pass  # Orchestrator caught SIGINT itself and will broadcast shutdown
    finally:
        # Give PC nodes a moment to receive the Zenoh shutdown message
        time.sleep(2.0)
        # Force-terminate any PC nodes that didn't exit on their own
        for proc in pc_procs:
            if proc.poll() is None:
                proc.terminate()
        print("group4os session ended.")


if __name__ == "__main__":
    main()
