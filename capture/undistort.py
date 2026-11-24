"""Fisheye / pinhole undistortion from calibrate_camera.py output (CPU remap or GPU grid_sample)."""
import numpy as np


class Undistort:
    """camera.json from calibrate_camera.py -> remap every frame to an undistorted pinhole view of `hfov` deg horizontal (out_w x out_h).
    The model was trained on an undistorted ~128 deg pinhole camera; a 120-160 deg fisheye cannot be used raw."""
    def __init__(self, calib_path, hfov=120.0, out_w=None, out_h=None):
        import cv2, json, math
        c = json.load(open(calib_path)); W, H = c["size"]; K = np.array(c["K"]); D = np.array(c["D"]); ow, oh = out_w or W, out_h or H
        f = (ow / 2) / math.tan(math.radians(hfov) / 2); P = np.array([[f, 0, ow / 2], [0, f, oh / 2], [0, 0, 1]])
        if c["model"] == "fisheye": self.m1, self.m2 = cv2.fisheye.initUndistortRectifyMap(K, D.reshape(4, 1), np.eye(3), P, (ow, oh), cv2.CV_16SC2)
        else: self.m1, self.m2 = cv2.initUndistortRectifyMap(K, D, np.eye(3), P, (ow, oh), cv2.CV_16SC2)
        self.cv2 = cv2; self.hfov = hfov
        self.calib = c; self.P = P; self.K, self.D, self.out = K, D, (ow, oh); self.size = (W, H)
    def __call__(self, rgb): return self.cv2.remap(rgb, self.m1, self.m2, self.cv2.INTER_LINEAR, borderMode=self.cv2.BORDER_CONSTANT)

    def gpu(self, dev="cuda"):
        """Same remap as __call__ on the GPU (grid_sample on the uploaded frame): on the Orin cv2.remap of a 1640x1232 frame costs ~10+ ms of
        one CPU core, the GPU does it in well under 1 ms. Returns f((B,3,H,W) float) -> (B,3,oh,ow)."""
        import torch, torch.nn.functional as F
        cv2 = self.cv2; W, H = self.size; ow, oh = self.out
        if self.calib["model"] == "fisheye": mx, my = cv2.fisheye.initUndistortRectifyMap(self.K, self.D.reshape(4, 1), np.eye(3), self.P, (ow, oh), cv2.CV_32FC1)
        else: mx, my = cv2.initUndistortRectifyMap(self.K, self.D, np.eye(3), self.P, (ow, oh), cv2.CV_32FC1)
        g = torch.from_numpy(np.stack(((mx + 0.5) / W * 2 - 1, (my + 0.5) / H * 2 - 1), -1)).float()[None].to(dev)     # cv2 map = source px centre; grid_sample align_corners=False
        f = lambda x: F.grid_sample(x, g.expand(x.shape[0], -1, -1, -1), mode="bilinear", padding_mode="zeros", align_corners=False)
        f.grid = g      # Update 166: GatePerception fuses NV12 -> RGB with this remap (pfm_runtime._prep, nv12_grid)
        return f
