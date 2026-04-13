import zenoh
import cv2
import numpy as np
import json
import sys
import os

# Add root to path for utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from utils import load_config, get_zenoh_config

def main():
    config = load_config()
    
    print("Connecting to Zenoh as PC (Video Rec)...")
    z_config = get_zenoh_config("listen")
    session = zenoh.open(z_config)

    
    # Track heartbeats for display
    node_stats = {}

    def heartbeat_handler(sample):
        try:
            hb = json.loads(bytes(sample.payload).decode('utf-8'))
            node_stats[hb['node']] = hb
        except Exception as e:
            print(f"Error parsing heartbeat: {e}")

    def video_handler(sample):
        try:
            # Decode JPEG buffer
            nparr = np.frombuffer(bytes(sample.payload), np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Add status overlay
                y_offset = 30
                for node, stats in node_stats.items():
                    status_str = f"{node}: {stats['status']} (CPU: {stats['cpu_percent']}%)"
                    cv2.putText(frame, status_str, (10, y_offset), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    y_offset += 30
                
                cv2.imshow("group4os - Video Stream", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    return
        except Exception as e:
            print(f"Error processing frame: {e}")

    # Subscribe to video
    print("Subscribing to 'felix/video'...")
    sub_video = session.declare_subscriber(config['topics']['video'], video_handler)
    
    # Subscribe to heartbeats
    print("Subscribing to 'felix/nodes/*'...")
    sub_hb = session.declare_subscriber(f"{config['topics']['heartbeat']}/*", heartbeat_handler)
    
    print("Video Receiver started. Press 'q' to exit.")
    
    try:
        while True:
            # Main thread keeps OpenCV window responsive
            pass
    except KeyboardInterrupt:
        print("Stopping PC Video Receiver...")
    finally:
        cv2.destroyAllWindows()
        session.close()

if __name__ == "__main__":
    main()
