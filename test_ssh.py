import json
import sys
from fabric import Connection

def test_connection():
    """
    Diagnostic script to verify SSH connectivity from this PC to the Raspberry Pi.
    Uses credentials defined in config.json.
    """
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        pi_cfg = config['nodes']['pi']
        print(f"--- group4os Connection Diagnostic ---")
        print(f"Target: {pi_cfg['ip']} ({pi_cfg['user']})")
        
        # We use strict settings here to bypass agent/key search issues
        # that commonly cause timeouts in Windows environments.
        conn = Connection(
            host=pi_cfg['ip'],
            user=pi_cfg['user'],
            connect_kwargs={
                "password": pi_cfg['ssh_pass'],
                "look_for_keys": False,
                "allow_agent": False,
                "timeout": 10
            }
        )
        
        print("Attempting to run 'whoami'...")
        result = conn.run("whoami", hide=True, timeout=10)
        
        print(f"SUCCESS: Logged in as '{result.stdout.strip()}'")
        print("The SSH bridge is correctly configured.")
        
    except Exception as e:
        print(f"\nFAILURE: {type(e).__name__}")
        print(f"Message: {e}")
        print("\nPossible fixes:")
        print("1. Ensure Tailscale is active and the Pi is pingable.")
        print("2. Verify the 'nodes.pi.ip' and 'nodes.pi.ssh_pass' in config.json.")
        print("3. Check if the Pi allows password authentication over SSH.")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
