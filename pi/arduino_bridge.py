import zenoh
import json
import time
import sys
import os
import threading
import serial
import math

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_heartbeat, get_zenoh_config, register_signals


def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    ard = config['arduino']
    port             = ard['serial_port']
    baud             = ard['serial_baud']
    wheel_radius     = ard['wheel_radius']
    wheel_separation = ard['wheel_separation']
    # meters of travel per encoder tick
    ticks_to_meters  = (2.0 * math.pi * wheel_radius) / (ard['encoder_cpr'] * ard['gear_ratio'])

    print(f"Opening {port} @ {baud} baud...", flush=True)
    try:
        ser = serial.Serial(port, baud, timeout=1.0)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open serial port {port}: {e}", flush=True)
        return

    # Wait for Arduino to reset (DTR toggle on connect triggers reset)
    time.sleep(2.0)
    ser.reset_input_buffer()
    print("Serial open — waiting for ACK:SYSTEM_READY...", flush=True)

    # ---- Zenoh setup ----
    z_config = get_zenoh_config("connect")
    session = zenoh.open(z_config)

    pub_odom = session.declare_publisher(config['topics']['odom'])
    pub_hb   = session.declare_publisher(f"{config['topics']['heartbeat']}/arduino")

    # ---- Shared state ----
    tick_lock  = threading.Lock()
    ticks      = {'fr': 0, 'rl': 0}   # cumulative encoder counts
    ser_lock   = threading.Lock()      # guard serial writes
    last_speed = [None]                # track last sent speed to avoid flooding

    # ---- cmd_vel subscriber: PC → Arduino ----
    # WORKAROUND: Arduino firmware has Q (CCW) and E (CW) rotation directions
    # physically inverted — the motor wiring or encoder polarity causes the robot
    # to spin CW when sent 'q' and CCW when sent 'e'.  Rather than reflash the
    # Arduino, we swap them here so the UI remains intuitive (Q=CCW, E=CW).
    _ROTATION_SWAP = {'q': 'e', 'e': 'q'}

    def cmd_handler(sample):
        """
        Expects JSON: {"cmd": "w", "speed": 150}
        Commands: w s a d q e x r  (match Arduino's lowercase protocol)
        Speed-only update: {"cmd": "speed", "speed": 150}
        """
        try:
            msg  = json.loads(bytes(sample.payload).decode('utf-8'))
            cmd  = _ROTATION_SWAP.get(msg.get('cmd', 'x'), msg.get('cmd', 'x'))
            speed = int(msg.get('speed', 150))

            with ser_lock:
                if cmd == 'speed':
                    ser.write(f"speed:{speed}\n".encode())
                    last_speed[0] = speed
                else:
                    # Send speed update only when it changes
                    if speed != last_speed[0]:
                        ser.write(f"speed:{speed}\n".encode())
                        last_speed[0] = speed
                    ser.write(f"{cmd}\n".encode())
        except Exception as e:
            print(f"cmd_handler error: {e}", flush=True)

    def shutdown_handler(_sample):
        print("Shutdown received.", flush=True)
        stop_event.set()

    subs = [
        session.declare_subscriber(config['topics']['cmd_vel'],  cmd_handler),
        session.declare_subscriber(config['topics']['shutdown'], shutdown_handler),
    ]

    # ---- Serial read thread: Arduino → ticks ----
    def read_serial():
        while not stop_event.is_set():
            try:
                # serial.Serial timeout=1.0 means readline returns after 1s with no data
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                if line.startswith('ACK:'):
                    print(f"Arduino: {line}", flush=True)
                elif line.startswith('E:'):
                    parts = line[2:].split(',')
                    if len(parts) == 2:
                        with tick_lock:
                            ticks['fr'] = int(parts[0])
                            ticks['rl'] = int(parts[1])
            except Exception:
                pass

    threading.Thread(target=read_serial, daemon=True).start()

    # ---- Odometry state ----
    # Robot has encoders on FR (front-right, M1) and RL (rear-left, M4).
    # Treated as right/left wheels for differential drive kinematics.
    # NOTE: strafing (a/d) is not observable with only a diagonal encoder pair.
    x = y = theta = 0.0
    prev_fr = prev_rl = 0
    last_hb_time = 0.0

    print("Arduino Bridge active. Publishing to felix/odom at 20Hz.", flush=True)

    try:
        while not stop_event.is_set():
            now = time.time()

            with tick_lock:
                cur_fr = ticks['fr']
                cur_rl = ticks['rl']

            # Delta ticks → meters (FR = right, RL = left)
            delta_right = (cur_fr - prev_fr) * ticks_to_meters
            delta_left  = (cur_rl - prev_rl) * ticks_to_meters
            prev_fr = cur_fr
            prev_rl = cur_rl

            dist   = (delta_left + delta_right) / 2.0
            dtheta = (delta_right - delta_left) / wheel_separation

            x     += dist * math.cos(theta + dtheta / 2.0)
            y     += dist * math.sin(theta + dtheta / 2.0)
            theta  = (theta + dtheta + math.pi) % (2.0 * math.pi) - math.pi

            pub_odom.put(json.dumps({
                'x':        round(x, 4),
                'y':        round(y, 4),
                'theta':    round(math.degrees(theta), 2),
                'ticks_fr': cur_fr,
                'ticks_rl': cur_rl,
            }))

            if now - last_hb_time > 2.0:
                pub_hb.put(json.dumps(get_heartbeat("Arduino")))
                last_hb_time = now

            stop_event.wait(0.05)  # 20 Hz odometry loop

    finally:
        # Stop motors before closing serial
        with ser_lock:
            try:
                ser.write(b"x\n")
            except Exception:
                pass
        del subs
        session.close()
        ser.close()
        print("Arduino Bridge stopped.", flush=True)


if __name__ == "__main__":
    main()
