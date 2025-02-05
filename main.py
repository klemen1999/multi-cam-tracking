import cv2
import time
import depthai as dai
from birdseyeview import BirdsEyeView
from camera import Camera
from typing import List
from tracker import Tracker
from multi_camera_sync import MultiCameraSync

device_infos = dai.Device.getAllAvailableDevices()
if len(device_infos) == 0:
    raise RuntimeError("No devices found!")
else:
    print("Found", len(device_infos), "devices")

device_infos.sort(key=lambda x: x.getMxId(), reverse=True) # sort the cameras by their mxId

cameras: List[Camera] = []

friendly_id = 0
for device_info in device_infos:
    friendly_id += 1
    cameras.append(Camera(device_info, friendly_id, show_video=True))

selected_camera = cameras[0]

def select_camera(friendly_id: int):
    global selected_camera

    i = friendly_id - 1
    if i >= len(cameras) or i < 0: 
        return None

    selected_camera = cameras[i]
    print(f"Selected camera {friendly_id}")

    return selected_camera

select_camera(1)

devices = [c.friendly_id for c in cameras]
multi_cam_sync = MultiCameraSync(devices, 0.01)
tracker = Tracker(
    devices = devices,
    multi_cam_max_dist=2,
    multi_cam_assoc_coef=0.7, #0.5 
    multi_cam_assoc_thresh=0.7,
    embedder=None,
    max_age=1000,
    nms_max_overlap=1,
)
birds_eye_view = BirdsEyeView(cameras, 512, 512, 100)

time.sleep(2) # wait for cameras to settle in

while True:
    key = cv2.waitKey(1)

    # QUIT - press `q` to quit
    if key == ord('q'):
        break
    
    # CAMERA SELECTION - use the number keys to select a camera
    if key >= ord('1') and key <= ord('9'):
        select_camera(key - ord('1') + 1)

    # POSE ESTIMATION - press `p` to start pose estimation
    if key == ord('p'):
        selected_camera.capture_pose_estimation_frame()

    # TOGGLE DEPTH VIEW - press `d` to toggle depth view
    if key == ord('d'):
        for camera in cameras:
            camera.show_detph = not camera.show_detph

    for camera in cameras:
        camera.update()
        if camera.frame_color:
            multi_cam_sync.add_msg({
                "timestamp": camera.frame_color.getTimestamp(), 
                "detections": camera.detected_objects
            }, camera.friendly_id)
   
    msgs = multi_cam_sync.get_msgs()
    if not msgs:
        continue

    tracks, objects = tracker.update(msgs)

    for camera in cameras:
        camera.render_tracks(tracks[camera.friendly_id])

    birds_eye_view.render(tracks, objects)



        