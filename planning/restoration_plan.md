# Plan: Restoring Reliable Video Stream with Pilot HUD Aesthetics

**Summary**
The current "Go Crazy" H.264 video pipeline is excellent for performance but has introduced a regressive bug in the Web Dashboard (blank/frozen stream). This plan restores the rock-solid reliability of the original website by stabilizing the PC-side "Transcoding Bridge." We will keep the hardware-accelerated H.264 on the Pi but ensure the Website serves a browser-friendly MJPEG stream using a non-blocking buffer.

---

**Implementation Steps**

### Phase 1: PC-Side Transcoder Stabilization
1.  **Modify `dashboard_server.py`**:
    - Replace the blocking `Queue` with a non-blocking `threading.Lock` + `current_frame` global variable.
    - Mirror the exact `PyAV` parsing/decoding loop that works in `video_receiver_osd.py`.
    - Ensure the `gen_frames()` generator never yields `None` to prevent browser timeouts.
2.  **Add Frame Health Monitoring**:
    - Implement a `last_frame_time` check to detect and report stream drops to the terminal.

### Phase 2: Pi-Side Bitstream Tuning
1.  **Modify `video_publisher.py`**:
    - Update the `ffmpeg` command to include `-tune zerolatency`.
    - Increase the `GOP` frequency to ensure the PC decoder can sync almost instantly when the website is opened.

### Phase 3: Pilot UI Preservation
1.  **Verify `index.html`**:
    - Ensure the HUD elements (Temp, CPU) remain anchored with the correct transparent styling.
    - Connect the "Mission Counter" to the new Zenoh telemetry topics.

---

**Dependencies**
- `av` (PyAV): PC-side H.264 decoding.
- `cv2` (OpenCV): PC-side JPEG re-encoding for MJPEG stream.
- `h264_v4l2m2m`: Pi hardware encoder.

---

**Verification**
- **Manual Check**: Launch `start_all.py` and verify `http://localhost:5000` shows video within 1 second of "Mission Active" log.
- **Stability Test**: Refresh the browser 5 times rapidly; the video should "snap" back instantly without crashing the backend.

---

**Skill Application Map**
- **log-changes**: Log the fix for the Vision Regression.
- **pi-communication**: Synchronize the Pi-side tuning changes via SSH.

---

**Decisions / Assumptions**
- **PC-Side Transcoding**: We assume the PC (Mission Control) has significant CPU headroom to handle a single H.264 -> JPEG transcode (~5% CPU usage).
- **No Pi Reversion**: We will NOT revert the Pi to software JPEG as it would spike CPU to 100%.

---

**Open Questions**
- None. The OSD success proves the H.264 data is valid; only the Bridge needs stabilization.
