import zenoh
import json
import time
import sys
import os
import threading
import keyboard

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_zenoh_config, register_signals

config      = load_config()
stop_event  = threading.Event()

pub_cmd_vel   = None
pub_lock      = threading.Lock()
control_on    = True
current_speed = [150]
desired_cmd   = [None]   # None = idle
held_keys     = set()

KEY_MAP = {
    'w': 'w', 's': 's', 'a': 'a', 'd': 'd',
    'q': 'q', 'e': 'e',
    'up': 'w', 'down': 's', 'left': 'a', 'right': 'd',
}
MOVE_CMDS = {'w', 's', 'a', 'd', 'q', 'e'}

CMD_LABELS = {
    'w': 'FORWARD', 's': 'REVERSE', 'a': 'STRAFE LEFT', 'd': 'STRAFE RIGHT',
    'q': 'ROTATE CCW', 'e': 'ROTATE CW', 'x': 'STOP', 'r': 'RESET TICKS',
}


def _print_status():
    cmd    = desired_cmd[0]
    state  = 'ON ' if control_on else 'OFF'
    action = CMD_LABELS.get(cmd, 'IDLE') if cmd else 'IDLE'
    line   = (f"\r[CTRL:{state}]  Speed:{current_speed[0]:3d}/255  "
              f"Cmd:{action:<14}  "
              f"(` toggle  +/- speed  Ctrl+C quit)   ")
    sys.stdout.write(line)
    sys.stdout.flush()


def _send(cmd):
    with pub_lock:
        p = pub_cmd_vel
    if p is not None:
        try:
            p.put(json.dumps({'cmd': cmd, 'speed': current_speed[0]}))
        except Exception as e:
            sys.stdout.write(f"\n[send] error: {e}\n")
            sys.stdout.flush()


def on_key_press(event):
    global control_on
    k = event.name.lower()

    # toggle control on/off with backtick
    if k == '`':
        control_on = not control_on
        if not control_on:
            desired_cmd[0] = None
            held_keys.clear()
        _print_status()
        return

    if not control_on:
        return

    if k in ('+', '='):
        current_speed[0] = min(255, current_speed[0] + 10)
        _print_status()
        return

    if k == '-':
        current_speed[0] = max(0, current_speed[0] - 10)
        _print_status()
        return

    if k == 'r':
        _send('r')
        _print_status()
        return

    if k == 'x':
        desired_cmd[0] = None
        held_keys.clear()
        _print_status()
        return

    cmd = KEY_MAP.get(k)
    if cmd and cmd in MOVE_CMDS:
        held_keys.add(k)
        desired_cmd[0] = cmd
        _print_status()


def on_key_release(event):
    if not control_on:
        return
    k   = event.name.lower()
    cmd = KEY_MAP.get(k)
    held_keys.discard(k)

    if cmd and cmd == desired_cmd[0]:
        # check if another move key is still held
        for hk in held_keys:
            c = KEY_MAP.get(hk)
            if c and c in MOVE_CMDS:
                desired_cmd[0] = c
                _print_status()
                return
        desired_cmd[0] = None
        _print_status()


def send_loop():
    """Runs at 4 Hz — re-sends active command to keep Arduino watchdog fed."""
    last_cmd = None
    while not stop_event.is_set():
        cmd = desired_cmd[0]
        if cmd != last_cmd:
            if cmd in MOVE_CMDS:
                _send(cmd)
            elif last_cmd in MOVE_CMDS:
                _send('x')
            last_cmd = cmd
        elif cmd in MOVE_CMDS:
            _send(cmd)
        stop_event.wait(0.25)


def zenoh_worker():
    global pub_cmd_vel
    while not stop_event.is_set():
        session = None
        try:
            z_config = get_zenoh_config("connect")
            session  = zenoh.open(z_config)
            with pub_lock:
                pub_cmd_vel = session.declare_publisher(config['topics']['cmd_vel'])
            sys.stdout.write("\n[zenoh] Connected.\n")
            sys.stdout.flush()
            _print_status()
            stop_event.wait()
        except Exception as e:
            sys.stdout.write(f"\n[zenoh] ERROR: {e} — reconnecting in 3s\n")
            sys.stdout.flush()
            with pub_lock:
                pub_cmd_vel = None
            time.sleep(3.0)
        finally:
            with pub_lock:
                pub_cmd_vel = None
            if session:
                try:
                    session.close()
                except Exception:
                    pass


def main():
    register_signals(stop_event)

    print("GROUP4OS Drive Controller")
    print("=" * 57)
    print("  Move:    W/S/A/D  or  Arrow Keys")
    print("  Rotate:  Q (CCW)  /  E (CW)")
    print("  Stop:    X")
    print("  Reset:   R (encoder ticks)")
    print("  Speed:   + / -  (step 10, range 0-255)")
    print("  Toggle:  ` (backtick) — pause/resume control")
    print("  Quit:    Ctrl+C")
    print("=" * 57)
    print("Connecting to Zenoh...", flush=True)

    threading.Thread(target=zenoh_worker, daemon=True).start()
    threading.Thread(target=send_loop,    daemon=True).start()

    keyboard.on_press(on_key_press)
    keyboard.on_release(on_key_release)

    _print_status()

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()

    print("\nDrive Controller stopped.", flush=True)


if __name__ == "__main__":
    main()
