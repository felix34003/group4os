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

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from utils import load_config, get_zenoh_config, register_signals

app = Flask(__name__)

frame_queue = Queue(maxsize=1)
node_stats  = {}
odom_data   = {}
pub_cmd_vel = None
config      = load_config()
stop_event  = threading.Event()

codec = av.CodecContext.create('h264', 'r')


def _draw_osd(img):
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
        temp     = stats.get('temp', '--')
        cpu      = stats.get('cpu_percent', '--')
        last_c   = stats.get('last_counter', '0')
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
            for frame in codec.decode(packet):
                img = frame.to_ndarray(format='bgr24')
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
        session.declare_subscriber(config['topics']['video'],            video_handler),
        session.declare_subscriber(f"{config['topics']['heartbeat']}/*", heartbeat_handler),
        session.declare_subscriber(config['topics']['odom'],             odom_handler),
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
