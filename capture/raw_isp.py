"""GPU ISP for the IMX219 raw frames (same steps as PerceptionModel's runtime). Input: uint16 (H, W) RGGB, value = 10-bit << 6, black ~4096.
Steps: black level -> odd-row shift fix (8 px for full-width x2-binned modes) -> Malvar-He-Cutler demosaic -> grey-world white balance (EMA)
-> colour matrix -> chroma denoise -> digital gain to 18 % grey (EMA) -> gamma 1/2.2 -> optional undistort grid -> optional rotation.
    isp = RawISP(); rgb = isp(raw)            # (1,3,H,W) float 0..1 on the GPU; isp.lin = linear grey level (for auto exposure)"""
import numpy as np, torch, torch.nn.functional as F


class RawISP:
    def __init__(self, dev="cuda", row_shift=None, grid=None, rotate=0):
        self.dev, self.row_shift, self.grid, self.rotate = dev, row_shift, grid, rotate; self._c = None; self.lin = None

    def _setup(self, H, W):
        d = self.dev; m = torch.zeros(4, H, W, device=d)
        m[0, 0::2, 0::2] = 1; m[1, 0::2, 1::2] = 1; m[2, 1::2, 0::2] = 1; m[3, 1::2, 1::2] = 1          # R, Gr, Gb, B
        kG = torch.tensor([[0, 0, -1, 0, 0], [0, 0, 2, 0, 0], [-1, 2, 4, 2, -1], [0, 0, 2, 0, 0], [0, 0, -1, 0, 0]], dtype=torch.float32) / 8
        kRow = torch.tensor([[0, 0, .5, 0, 0], [0, -1, 0, -1, 0], [-1, 4, 5, 4, -1], [0, -1, 0, -1, 0], [0, 0, .5, 0, 0]], dtype=torch.float32) / 8
        kX = torch.tensor([[0, 0, -1.5, 0, 0], [0, 2, 0, 2, 0], [-1.5, 0, 6, 0, -1.5], [0, 2, 0, 2, 0], [0, 0, -1.5, 0, 0]], dtype=torch.float32) / 8
        k = torch.stack((kG, kRow, kRow.t().contiguous(), kX))[:, None].to(d)
        ccm = torch.tensor([[1.70, -0.50, -0.20], [-0.35, 1.60, -0.25], [-0.05, -0.55, 1.60]], device=d)
        self._c = ((H, W), m, k, ccm); self.wb = torch.ones(3, device=d); self.dgain = torch.ones((), device=d)

    @torch.no_grad()
    def __call__(self, frame):
        H, W = frame.shape
        if self._c is None or self._c[0] != (H, W): self._setup(H, W)
        _, m, k, ccm = self._c
        u = torch.from_numpy(np.ascontiguousarray(frame).view(np.int16)).to(self.dev).to(torch.int32).bitwise_and_(0xFFFF)
        x = (u.float() - 4096.0).clamp_(min=0).mul_(1.0 / (65535.0 - 4096.0))
        sh = self.row_shift if self.row_shift is not None else (8 if W == 1640 else 0)
        if sh:   # row y comes out sh*(y%4) px LEFT (x2-binned full-width readout, factory mode too): shift classes 1,2,3 by sh, 2sh, 3sh
            x = x.clone()
            for c_ in (1, 2, 3): d_ = sh * c_; x[c_::4, d_:] = x[c_::4, :-d_].clone(); x[c_::4, :d_] = x[c_::4, d_:d_ + 1]
        c = F.conv2d(F.pad(x[None, None], (2, 2, 2, 2), mode="reflect"), k)[0]
        R_, Gr, Gb, B_ = m
        r = x * R_ + c[1] * Gr + c[2] * Gb + c[3] * B_; g = x * (Gr + Gb) + c[0] * (R_ + B_); b = x * B_ + c[1] * Gb + c[2] * Gr + c[3] * R_
        rgb = torch.stack((r, g, b))[None].clamp_(min=0); mean = rgb[0, :, ::8, ::8].mean((1, 2))
        self.wb.mul_(0.9).add_(0.1 * (mean[1] / mean.clamp(min=1e-4)).clamp(0.4, 3.0)); self.lin = float((mean * self.wb).mean())
        self.dgain.mul_(0.9).add_(0.1 * torch.clamp(0.18 / (mean * self.wb).mean().clamp(min=1e-4), 0.5, 16.0))
        rgb = torch.einsum("ij,bjhw->bihw", ccm, rgb * (self.wb * self.dgain).view(1, 3, 1, 1))
        yy = rgb.mean(1, keepdim=True); rgb = (yy + F.avg_pool2d(rgb - yy, 5, 1, 2, count_include_pad=False)).clamp_(0, 1).pow_(1 / 2.2)
        # comb / row-alternation of the x2-binned readout: vertical [1,2,1]/4 (measured: comb 38 -> 15, noise 47 -> 26, sharpness 32 -> 20),
        # then a light edge-preserving luma denoise (guided filter on luma, r 1, eps 5e-4)
        rgb = torch.cat((rgb[:, :, :1], 0.25 * rgb[:, :, :-2] + 0.5 * rgb[:, :, 1:-1] + 0.25 * rgb[:, :, 2:], rgb[:, :, -1:]), 2)
        Y = rgb.mean(1, keepdim=True); mY = F.avg_pool2d(Y, 3, 1, 1, count_include_pad=False); vY = F.avg_pool2d(Y * Y, 3, 1, 1, count_include_pad=False) - mY * mY
        A = vY / (vY + 5e-4); Bc = mY - A * mY; Yn = F.avg_pool2d(A, 3, 1, 1, count_include_pad=False) * Y + F.avg_pool2d(Bc, 3, 1, 1, count_include_pad=False)
        rgb = (rgb + (Yn - Y)).clamp_(0, 1)
        if self.grid is not None: rgb = F.grid_sample(rgb, self.grid, mode="bilinear", padding_mode="zeros", align_corners=False)
        if self.rotate: rgb = torch.rot90(rgb, k=-self.rotate // 90, dims=(2, 3))
        return rgb
