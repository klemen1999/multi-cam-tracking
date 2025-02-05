import depthai as dai
import cv2
import numpy as np
from typing import Tuple
import os

class Calibration:
    def __init__(self, checkerboard_size: Tuple[int, int], square_size: float, device: dai.Device):
        self.checkerboard_size = checkerboard_size
        self.checkerboard_inner_size = (checkerboard_size[0] - 1, checkerboard_size[1] - 1)
        self.square_size = square_size
        self.device = device
        self.device_info = device.getDeviceInfo()

        self.corners_world = np.zeros((1, self.checkerboard_inner_size[0] * self.checkerboard_inner_size[1], 3), np.float32)
        self.corners_world[0,:,:2] = np.mgrid[0:self.checkerboard_inner_size[0], 0:self.checkerboard_inner_size[1]].T.reshape(-1, 2)
        self.corners_world *= square_size

        self.last_frame_gray = None

        self.intrinsic_mat = None
        self.distortion_coef = None
        self.rot_vec = None
        self.trans_vec = None
        self.world_to_cam = None
        self.cam_to_world = None
        self.position = None

        self.load_calibration_from_camera()
        self.load_pose_from_file()

    def find_checkerboard_corners(self, frame_gray: cv2.Mat):
        print("Finding checkerboard corners...")

        found, corners = cv2.findChessboardCorners(
            frame_gray, self.checkerboard_inner_size, 
            cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_FAST_CHECK + cv2.CALIB_CB_NORMALIZE_IMAGE
        )

        if not found:
            return None

        corners = cv2.cornerSubPix(
            frame_gray, corners, (11, 11), (-1, -1), 
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        )

        return corners

    def compute_transformations(self, rvec, tvec):
        rotM = cv2.Rodrigues(rvec)[0]
        self.world_to_cam = np.vstack((np.hstack((rotM, tvec)), np.array([0,0,0,1])))
        self.cam_to_world = np.linalg.inv(self.world_to_cam)
        self.position = (self.cam_to_world @ np.array([[0,0,0,1]]).T)[:3]

    def compute_pose_estimation(self, frame_rgb: cv2.Mat, frame_gray: cv2.Mat):
        if self.intrinsic_mat is None or self.distortion_coef is None:
            print("No calibration parameters. Cannot compute pose estimation.")
            return None

        corners = self.find_checkerboard_corners(frame_gray)
        if corners is None:
            print("No checkerboard found")
            return None

        ret, rvec, tvec = cv2.solvePnP(
            self.corners_world, corners, self.intrinsic_mat, self.distortion_coef
        )

        self.compute_transformations(rvec, tvec)

        print("POSE ESTIMATION DONE")
        print("ret: ", ret)
        print("Rotation vector : \n", rvec)
        print("Translation vector : \n", tvec)
        print("Camer to World transformation matrix : \n", self.cam_to_world)

        self.rot_vec = rvec
        self.trans_vec = tvec

        self.save_pose_to_file()

        return self.draw_origin(frame_rgb)

    def draw_origin(self, frame_rgb: cv2.Mat):
        points, _ = cv2.projectPoints(
            np.float64([[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0], [0, 0, -0.1]]), 
            self.rot_vec, self.trans_vec, self.intrinsic_mat, self.distortion_coef
        )
        [p_0, p_x, p_y, p_z] = points.astype(np.int64)

        reprojection = frame_rgb.copy()
        reprojection = cv2.line(reprojection, p_0[0], p_x[0], (0, 0, 255), 5)
        reprojection = cv2.line(reprojection, p_0[0], p_y[0], (0, 255, 0), 5)
        reprojection = cv2.line(reprojection, p_0[0], p_z[0], (255, 0, 0), 5)

        return reprojection
    
    def load_calibration_from_camera(self):
        self.intrinsic_mat = self.device.readCalibration().getCameraIntrinsics(dai.CameraBoardSocket.RGB, 3840, 2160)
        self.intrinsic_mat = np.array(self.intrinsic_mat)
        self.distortion_coef = np.zeros((1,5))

    def save_pose_to_file(self):
        os.makedirs("config", exist_ok=True)
        mxid = self.device_info.getMxId()
        rot_vec_filename = f"config/rot_vec.{mxid}.npy"
        trans_vec_filename = f"config/trans_vec.{mxid}.npy"

        try:
            np.save(rot_vec_filename, self.rot_vec)
            np.save(trans_vec_filename, self.trans_vec)
        except Exception as e:
            print("Could not save pose to file")
            print(e)
            return False

        print(f"Pose parameters saved to `{rot_vec_filename}` and `{trans_vec_filename}`.")

    def load_pose_from_file(self):
        mxid = self.device_info.getMxId()
        rot_vec_filename = f"config/rot_vec.{mxid}.npy"
        trans_vec_filename = f"config/trans_vec.{mxid}.npy"
        try:
            self.rot_vec = np.load(rot_vec_filename)
            self.trans_vec = np.load(trans_vec_filename)
            self.compute_transformations(self.rot_vec, self.trans_vec)
        except:
            print(f"Could not load calibration parameters from `{rot_vec_filename}` and `{trans_vec_filename}`.")
            return False

        print(f"Calibration parameters loaded from `{rot_vec_filename}` and `{trans_vec_filename}`.")
        return True