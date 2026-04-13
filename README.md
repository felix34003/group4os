# group4os | Robotics Middleware

group4os is a cross-platform robotics bridge connecting a Windows workstation to a Raspberry Pi over **Zenoh 1.0** pub/sub and **Tailscale VPN**. It streams live H.264 video, publishes differential-drive odometry, and exposes a browser-based mission control dashboard with real-time drive control.

---

## System Architecture

```
  ┌──────────────────────────────────────────────────────────────┐
  │  PC (Workstation)                                            │
  │                                                              │
  │  orchestrator.py ─────── felix/control/shutdown ──►         │
  │       │                                                      │
  │       ├── counter_publisher.py   pub: felix/counter          │
  │       └── dashboard_server.py    sub: felix/video            │
  │               │                  sub: felix/nodes/*          │
  │               │                  sub: felix/odom             │
  │               │                  pub: felix/cmd_vel          │
  │               └── http://localhost:5000  (browser UI)        │
  └──────────────────────────────┬───────────────────────────────┘
                  Tailscale VPN  │  TCP/7447
  ┌──────────────────────────────▼───────────────────────────────┐
  │  Raspberry Pi                                                │
  │                                                              │
  │  video_publisher.py     pub: felix/video   (H.264 HW enc)   │
  │  counter_subscriber.py  sub: felix/counter                   │
  │  status_server.py       pub: felix/nodes/pi (heartbeat)      │
  │  arduino_bridge.py      sub: felix/cmd_vel                   │
  │                         pub: felix/odom                      │
  │                         pub: felix/nodes/arduino (heartbeat) │
  │                              │                               │
  │                         USB serial (115200 baud)             │
  │                              │                               │
  │                         Arduino Mega                         │
  │                         (motor controller + encoders)        │
  └──────────────────────────────────────────────────────────────┘
```

### Key design decisions

| Concern | Solution |
|---|---|
| Hanging processes | Every node holds a `threading.Event` `stop_event` wired to SIGINT/SIGTERM and the `felix/control/shutdown` Zenoh topic |
| Shutdown coordination | Orchestrator broadcasts `felix/control/shutdown`; all nodes receive it and exit cleanly |
| Pi always runs latest code | `start_all.py` SSH-syncs files to the Pi before any node launches |
| Node health visibility | All nodes publish heartbeats to `felix/nodes/<name>`; orchestrator tracks staleness |
| Video pipeline | Pi encodes H.264 via `h264_v4l2m2m` (hardware), streams raw bitstream over Zenoh; PC decodes with PyAV, burns OSD overlay, re-encodes as JPEG for MJPEG browser stream |
| Drive control | Browser POSTs `{cmd, speed}` JSON to Flask `/cmd` → published on `felix/cmd_vel` → Arduino bridge forwards over serial |
| Odometry | Arduino reports encoder ticks (`E:{fr},{rl}`) at 20 Hz; bridge computes differential-drive pose and publishes to `felix/odom` |

---

## Directory Structure

```
group4os/
├── start_all.py              # Entry point — syncs Pi, launches everything
├── config.json               # All IPs, topic names, video/counter/arduino config
├── utils.py                  # Shared: load_config, get_heartbeat, get_zenoh_config, register_signals
│
├── computer/
│   ├── orchestrator.py       # Master node: waits for all nodes, prints status, owns shutdown
│   ├── topics/
│   │   └── counter_publisher.py   # Publishes incrementing counter at configured Hz
│   └── website/
│       ├── dashboard_server.py    # Flask: H.264 decode → OSD → MJPEG; /odom /stats /cmd endpoints
│       └── templates/index.html   # Two-column dark dashboard: video+drive-control | odom+nodes
│
└── pi/
    ├── video_publisher.py    # FFmpeg H.264 HW encoder → felix/video
    ├── counter_subscriber.py # Receives counter, tracks last value
    ├── status_server.py      # Heartbeat: CPU, MEM, temp → felix/nodes/pi
    └── arduino_bridge.py     # Serial bridge: felix/cmd_vel → Arduino, encoder ticks → felix/odom
```

---

## Zenoh Topics

| Topic | Direction | Publisher | Subscribers | Payload |
|---|---|---|---|---|
| `felix/video` | Pi → PC | video_publisher | dashboard_server | Raw H.264 bitstream chunks |
| `felix/counter` | PC → Pi | counter_publisher | counter_subscriber | Plain integer string |
| `felix/nodes/*` | all → all | every node | orchestrator, dashboard_server | JSON heartbeat |
| `felix/control/shutdown` | PC → all | orchestrator | every node | empty |
| `felix/odom` | Pi → PC | arduino_bridge | dashboard_server | JSON `{x, y, theta, ticks_fr, ticks_rl}` |
| `felix/cmd_vel` | PC → Pi | dashboard_server | arduino_bridge | JSON `{cmd, speed}` |

---

## Drive Control

The browser dashboard sends discrete drive commands to the Arduino via the `felix/cmd_vel` topic. Commands can be sent by keyboard or by clicking/holding the on-screen D-pad.

| Key | Action | Arduino command |
|---|---|---|
| W / ↑ | Forward | `w` |
| S / ↓ | Reverse | `s` |
| A / ← | Strafe left | `a` |
| D / → | Strafe right | `d` |
| Q | Rotate CCW | `e` ¹ |
| E | Rotate CW | `q` ¹ |
| X | Stop | `x` |
| R | Reset encoder ticks | `r` |

> ¹ **Q/E are swapped in `arduino_bridge.py`** (`_ROTATION_SWAP = {'q':'e', 'e':'q'}`).
> The Arduino firmware has the rotation directions physically inverted (motor wiring or encoder
> polarity). Rather than reflashing, the bridge corrects this transparently so the UI stays
> intuitive (Q = CCW, E = CW).

Hold any movement key to keep moving; release to stop. Speed (0–255 PWM) is set with the slider and sent to the Arduino immediately on change.

---

## Odometry

The Arduino reports cumulative encoder ticks on the FR (front-right, M1) and RL (rear-left, M4) motors at 20 Hz over serial (`E:{fr},{rl}\n`). These form a diagonal pair treated as right/left wheels for standard differential-drive kinematics:

```
dist   = (Δleft + Δright) / 2
dtheta = (Δright − Δleft) / wheel_separation
x     += dist · cos(θ + dtheta/2)
y     += dist · sin(θ + dtheta/2)
```

> **Note:** Strafing (A/D) is not observable with only the diagonal encoder pair. Odometry
> accumulates only forward/reverse travel and rotation.

### Calibration

The wheel parameters in `config.json` will need tuning against the real robot:

```json
"arduino": {
    "wheel_radius":     0.04,   ← measure actual wheel radius (metres)
    "wheel_separation": 0.21,   ← measure centre-to-centre track width (metres)
    "encoder_cpr":      2.0,    ← pulses per revolution from encoder
    "gear_ratio":       30.0    ← motor gearbox ratio
}
```

**Quick calibration procedure:**
1. Click **R** (Reset Ticks) on the dashboard to zero the pose.
2. Drive the robot exactly 1 metre forward with **W**.
3. Check the **X (m)** odometry card — adjust `gear_ratio` proportionally until it reads `1.000`.

---

## Arduino Serial Protocol

Communication is over `/dev/arduino` (udev symlink → `ttyUSB0`, CH340 chip) at 115200 baud.

**PC → Arduino (commands sent as newline-terminated strings):**
```
w\n          Forward
s\n          Reverse
a\n          Strafe left
d\n          Strafe right
q\n          Rotate CCW (note: bridge sends 'e' due to firmware inversion — see Drive Control)
e\n          Rotate CW
x\n          Stop
r\n          Reset encoder ticks
speed:N\n    Set PWM speed (0–255); sent before any command when speed changes
```

**Arduino → PC (encoder feedback):**
```
E:{fr},{rl}\n    Cumulative encoder ticks, front-right and rear-left
ACK:*\n          Acknowledgement/status messages (logged, not processed)
```

The Arduino has a **1000 ms safety watchdog** — if no command is received for 1 second, motors stop automatically.

---

## Getting Started

### Requirements

**PC:**
```bash
pip install eclipse-zenoh flask opencv-python av psutil fabric
```

**Pi (installed automatically via `start_all.py` sync, but needed once):**
```bash
pip install eclipse-zenoh pyserial psutil
```

### Configuration

Edit `config.json` — the only values that change between machines:

| Field | What to set |
|---|---|
| `nodes.pc.ip` | This PC's Tailscale IP (`tailscale ip -4`) |
| `zenoh.connect[0]` | `tcp/<THIS_PC_TAILSCALE_IP>:7447` (must match `nodes.pc.ip`) |
| `nodes.pi.ip` | Pi's Tailscale IP |
| `nodes.pi.user` / `nodes.pi.ssh_pass` | Pi SSH credentials |
| `nodes.pi.venv` | Path to Python venv binary on the Pi |
| `arduino.serial_port` | Default `/dev/arduino`; change if udev symlink differs |

> **Moving to a new PC?** The only required changes are `nodes.pc.ip` and `zenoh.connect[0]`.
> Everything else (Pi IP, SSH creds, Arduino port) stays the same across machines.

### Verify Connection

Before launching the full system, verify that your PC can authenticate with the Raspberry Pi:

```bash
python test_ssh.py
```

If this fails with an `AuthenticationException`, check your credentials in `config.json` and ensure the Pi is reachable.

### Launch

```bash
python start_all.py
```

This will:
1. Ping the Pi
2. SSH in and kill any old group4os processes
3. Sync the latest code to the Pi
4. Start Pi nodes in the background (`video_publisher`, `counter_subscriber`, `status_server`, `arduino_bridge`)
5. Start PC nodes as subprocesses (`counter_publisher`, `dashboard_server`)
6. Run the orchestrator in the foreground

Open **http://localhost:5000** (auto-launched) for the mission control dashboard.

Press `Ctrl+C` to shut everything down cleanly across all nodes.

---

## Adding a New Node (e.g. IMU)

The architecture is built to scale. Adding a new sensor takes 4 steps:

**1. Add the topic to `config.json`:**
```json
"topics": {
    "imu": "felix/imu"
}
```

**2. Write the Pi script** (`pi/imu_publisher.py`):
```python
import zenoh, json, threading, sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils import load_config, get_heartbeat, get_zenoh_config, register_signals

def main():
    config = load_config()
    stop_event = threading.Event()
    register_signals(stop_event)

    session = zenoh.open(get_zenoh_config("connect"))
    pub_imu = session.declare_publisher(config['topics']['imu'])
    pub_hb  = session.declare_publisher(f"{config['topics']['heartbeat']}/imu")
    subs = [session.declare_subscriber(config['topics']['shutdown'], lambda _s: stop_event.set())]

    while not stop_event.is_set():
        pub_imu.put(json.dumps({"ax": 0.0, "ay": 0.0, "az": 9.8}))
        pub_hb.put(json.dumps(get_heartbeat("IMU")))
        stop_event.wait(0.01)  # 100 Hz

    del subs
    session.close()

if __name__ == "__main__":
    main()
```

**3. Register it in `start_all.py`:**
```python
PI_SYNC_FILES = [
    ...
    ("pi/imu_publisher.py", "pi/imu_publisher.py"),
]
pi_nodes = [
    ...
    "pi/imu_publisher.py",
]
```

**4. (Optional) Add to orchestrator's expected nodes:**
```python
EXPECTED_NODES = {"Pi", "PC", "IMU"}
```

The dashboard will automatically create a stat card for the new node the first time it sends a heartbeat — no dashboard changes needed.

---

## Known Hardware Quirks

| Issue | Workaround | Location |
|---|---|---|
| Q/E rotation inverted in Arduino firmware | `_ROTATION_SWAP = {'q':'e', 'e':'q'}` swaps commands before serial write | `pi/arduino_bridge.py` |
| Arduino resets on USB connect (DTR toggle) | `time.sleep(2.0)` after `serial.Serial()` before sending any commands | `pi/arduino_bridge.py` |
| Strafing not observable in odometry | Only FR+RL diagonal encoder pair fitted; A/D commands move the robot but don't update pose | `pi/arduino_bridge.py` |

---

## Performance

| Metric | Value |
|---|---|
| Video resolution | 640×480 |
| Target FPS | 30 |
| Pi CPU (video) | ~15% (`h264_v4l2m2m` hardware encoder) |
| PC CPU | ~5% |
| Odometry rate | 20 Hz |
| Dashboard poll (odom) | 200 ms |
| Dashboard poll (stats) | 1 s |

---

## Hardware Notes

- **Power:** Pi requires a quality **5V/3A** adapter. Undervoltage (throttle code `0x50005`) causes USB resets and camera failure.
- **Network:** All traffic routes through Tailscale. Ensure both devices are on the same tailnet before running `start_all.py`.
- **Arduino udev:** The CH340 USB-serial adapter is symlinked to `/dev/arduino` via `/etc/udev/rules.d/99-robot-hardware.rules`. The `ece_441` user must be in the `dialout` group.

---

Maintained at: [felix34003/group4os](https://github.com/felix34003/group4os)
