import zenoh
import json
import sys
import os
import time
import threading
import webbrowser
import av
import cv2
from flask import Flask, render_template, Response, jsonify, request
from queue import Queue, Empty
from ultralytics import YOLO

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from utils import load_config, get_zenoh_config, register_signals

app = Flask(__name__)

frame_queue = Queue(maxsize=1)
node_stats  = {}
odom_data   = {}
pub_cmd_vel = None          # set once zenoh_worker initialises
config      = load_config()
stop_event  = threading.Event()

codec = av.CodecContext.create('h264', 'r')

# YOLOv8n — downloads yolov8n.pt on first run (~6 MB).
# Uses CUDA automatically if available, otherwise CPU.
yolo = YOLO('yolov8n.pt')

# Colour palette: one BGR colour per class id (cycles every 80)
_PALETTE = [
    (56, 56, 255), (151, 157, 255), (31, 112, 255), (29, 178, 255),
    (49, 210, 207), (10, 249, 72),  (23, 204, 146), (134, 219, 61),
    (52, 147, 26),  (187, 212, 0),  (168, 153, 44), (255, 194, 0),
    (255, 130, 0),  (255, 56, 0),   (255, 56, 132), (255, 0, 178),
    (199, 0, 255),  (10, 10, 10),
]

def _class_color(cls_id):
    return _PALETTE[int(cls_id) % len(_PALETTE)]


def _draw_detections(img, results):
    """Draw bounding boxes and labels from a YOLO Results object."""
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf     = float(box.conf[0])
        cls_id   = int(box.cls[0])
        label    = f"{results.names[cls_id]} {conf:.2f}"
        color    = _class_color(cls_id)

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


def _draw_osd(img):
    """Burn node-stats overlay onto img in-place (same style as OSD window)."""
    row_h   = 35
    padding = 10
    box_h   = 30 + len(node_stats) * row_h + padding
    overlay = img.copy()
    cv2.rectangle(overlay, (5, 5), (315, box_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.5, img, 0.5, 0, img)
    cv2.putText(img, "GROUP4OS MISSION CONTROL [H.264]", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    y = 40
    for node, stats in node_stats.items():
        temp    = stats.get('temp', '--')
        cpu     = stats.get('cpu_percent', '--')
        last_c  = stats.get('last_counter', '0')
        temp_str = f"| {temp}C" if temp not in (0.0, '--') else ""
        cv2.putText(img, f"{node}: {cpu}% CPU {temp_str}", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        cv2.putText(img, f"STEP: {last_c}", (10, y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        y += 35


def video_handler(sample):
    try:
        packets = codec.parse(bytes(sample.payload))
        for packet in packets:
            frames = codec.decode(packet)
            for frame in frames:
                img = frame.to_ndarray(format='bgr24')
                results = yolo(img, verbose=False)[0]
                _draw_detections(img, results)
                _draw_osd(img)
                ok, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    continue
                data = jpg.tobytes()
                if frame_queue.full():
                    try:
                        frame_queue.get_nowait()
                    except Empty:
                        pass
                frame_queue.put_nowait(data)
    except Exception as e:
        print(f"[video_handler] ERROR: {e}", flush=True)


def heartbeat_handler(sample):
    try:
        hb = json.loads(bytes(sample.payload).decode('utf-8'))
        node_stats[hb['node']] = hb
    except Exception:
        pass


def odom_handler(sample):
    global odom_data
    try:
        odom_data = json.loads(bytes(sample.payload).decode('utf-8'))
    except Exception:
        pass


def zenoh_worker():
    global pub_cmd_vel
    print("Connecting to Zenoh...")
    z_config = get_zenoh_config("listen")
    session  = zenoh.open(z_config)

    pub_cmd_vel = session.declare_publisher(config['topics']['cmd_vel'])

    subs = [
        session.declare_subscriber(config['topics']['video'],               video_handler),
        session.declare_subscriber(f"{config['topics']['heartbeat']}/*",    heartbeat_handler),
        session.declare_subscriber(config['topics']['odom'],                odom_handler),
        session.declare_subscriber(config['topics']['shutdown'], lambda _s: stop_event.set()),
    ]

    print("Zenoh Bridge active.")
    stop_event.wait()
    del subs
    session.close()


def gen_frames():
    while not stop_event.is_set():
        try:
            frame = frame_queue.get(timeout=2.0)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Empty:
            continue


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/stats')
def stats():
    return jsonify(node_stats)


@app.route('/odom')
def odom():
    return jsonify(odom_data)


@app.route('/cmd', methods=['POST'])
def cmd():
    """
    Receive a drive command from the browser and publish it to felix/cmd_vel.
    Body: {"cmd": "w", "speed": 150}
    """
    data = request.get_json(silent=True)
    if pub_cmd_vel is not None and data:
        pub_cmd_vel.put(json.dumps(data))
    return jsonify({'ok': True})


def main():
    register_signals(stop_event)
    threading.Thread(target=zenoh_worker, daemon=True).start()

    def open_browser():
        time.sleep(2)
        print("Launching Dashboard...")
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    print("Starting group4os Mission Control on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)


if __name__ == "__main__":
    main()
