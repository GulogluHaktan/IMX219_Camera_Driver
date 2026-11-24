# IMX219 wide high-frame-rate modes (Jetson Orin NX, L4T R39.2.1)

Custom sensor modes for the IMX219 (Arducam / RPi-type, wide M12 lens) so the camera gives the **full horizontal field of view (~122°) at 60–84 fps**.
The stock driver offers full width only at 1640x1232 @ 30 and 60 fps only as a centre crop (1280x720, ~94°).

| slot | output | fps | readout |
|---|---|---|---|
| mode5 | 1640x864 | 60 | full width, x2 binning, rows 504..2231 (centred on the optical axis) |
| mode7 | 1640x616 | 84 | full width, x2 binning, rows 752..1983 (centred on the optical axis) |
| mode6 | 1640x616 | 84 | duplicate of mode7 (keeps the mode count / order) |

Measured: 59.98 / 84.11 fps, 0 discarded frames (raw V4L2).

## Repository layout
- `driver/` kernel module sources (`i2c/`), `build_on_orin.sh`, `make_overlay.py` (device-tree overlay from the stock one), `kamera_mod.sh` (switch stock / custom).
- `capture/` `v4l2raw.py` (zero-copy raw V4L2 capture + sensor exposure / gain), `raw_isp.py` (GPU ISP), `isp_cuda.py` (same ISP as CUDA kernels, 3.3 ms on the Orin), `raw_record.py` (record at full rate, convert to JPEG / mp4), `undistort.py`.
- `calib/` lens calibrations (fisheye model) for each mode, `calibrate_camera.py`, the 9x6 checkerboard image (3.2 cm squares on our screen).

## Quick start (on the Orin)
```bash
bash driver/build_on_orin.sh                 # build module + overlay into ~/imx219_backup
bash driver/kamera_mod.sh ham                # install custom modes (reboots); back: bash driver/kamera_mod.sh argus
sudo systemctl stop nvargus-daemon           # raw V4L2 and Argus cannot share the sensor
python3 capture/v4l2raw.py 7 5               # 5 s test: fps, drops
python3 capture/raw_record.py rec ~/rec1 --secs 10 --exp 2000 --gain 64
python3 capture/raw_record.py conv ~/rec1 --mp4 --calib calib/camera_imx219_cam1_1640x616.json --hfov 100
```
Python needs numpy, torch (CUDA) and opencv for `conv`; capture itself only needs numpy.

## How it is used
- **Argus / the NVIDIA ISP cannot use these modes** (and stops working for the camera while they are installed): Argus matches every
  sensor mode to a knobset in the encrypted `/var/nvidia/nvcam/settings/imx219.nito`. Frames are read raw through V4L2
  (`capture/v4l2raw.py`, `bypass_mode=0`, `sensor_mode=N`, frame rate set in a separate call after the mode switch) and converted on the GPU by
  our own ISP (`capture/raw_isp.py`, same as PerceptionModel `deploy/pfm_runtime.py: _prep_raw`: black level, odd-row shift fix, Malvar-He-Cutler demosaic, grey-world WB, colour matrix,
  chroma denoise, digital gain, gamma, undistort).
- Switch: `bash kamera_mod.sh ham` (custom) / `bash kamera_mod.sh argus` (stock) / `bash kamera_mod.sh durum`; each reboots the Orin.
- Build from source on the Orin: `bash build_on_orin.sh`, then `bash kamera_mod.sh ham`.
- Live perception on top of this camera: PerceptionModel repository (`deploy/run.py --source raw:7`, `deploy/car_test.sh`).
- Calibrations: `calib/camera_imx219_cam1_1640x616.json`, `..._1640x864.json` (same pixel scale as the 1640x1232 calibration, cy shifted).

## Sources
`i2c/nv_imx219.c`, `platform/tegra/camera/camera_gpio.h`: NVIDIA L4T R39.2.1 public sources (`kernel_oot_modules_src.tbz2`, GPL-2.0), unchanged.
`i2c/imx219_mode_tbls.h`: NVIDIA's table + our three modes (search "Update 167").

## Traps (each cost hours)
1. `inc/nvidia/conftest.h` **must define `NV_TEGRA_PMC_IO_PAD_POWER_ENABLE_PRESENT`** (NVIDIA backported `tegra_pmc_io_pad_power_enable` into
   their 6.8 kernel; the header comment says "Linux 7.0"). Without it `struct camera_common_data` is 8 bytes shorter: the module loads, but
   the VI discards every frame (`corr_err ... err_data 256`). Check a build: an unmodified `nv_imx219.c` must disassemble identically to the stock module.
2. Never `rmmod nv_imx219` while loaded (hung / rebooted the Orin): replace the file and reboot (`kamera_mod.sh`).
3. Raw RG10 data: uint16, value = 10-bit << 6, black level ~4096.
4. **Rows come out shifted left by 8·(y mod 4) px** (measured 0 / 9 / 16 / 23 px) in every x2-binned full-width readout, at any frame rate or
   exposure (also the stock 1640x1232 mode; Argus hides it; 1280x720 is clean). Fixing only the odd rows by 8 px leaves a comb pattern; the GPU ISP
   shifts row classes 1, 2, 3 back by 8, 16, 24 px (`raw_row_shift`, default 8 for width 1640).
4b. **Exposure / gain / frame rate are not forwarded to the sensor in raw V4L2 streaming**: `capture/v4l2raw.py` writes the IMX219 registers
   directly over I2C (0x0160 frame length, 0x015A coarse exposure in 18.9 µs lines, 0x0157 analog gain = 256 − 256/gain).
4c. `capture/isp_cuda.py`: the same ISP as five hand-written CUDA kernels (torch cpp_extension, compiled on first use): 3.3 ms per 1640x616 frame on
   the Orin NX vs 25 ms for the PyTorch version (max abs difference 0.05).
5. x4 binning (`0x0174 = 2`) or binning + skipping for 820x616 gives a 4-px even/odd row shift (sawtooth): rejected. 1640x720 gave black frames.
6. The first ~60 s after boot capture can fail spuriously; Argus and raw V4L2 cannot run at the same time (`sudo systemctl stop nvargus-daemon`).

## Licence
`driver/i2c/nv_imx219.c`, `driver/i2c/imx219_mode_tbls.h`, `driver/platform/tegra/camera/camera_gpio.h`: NVIDIA, GPL-2.0 (L4T public sources). The rest: same terms as the PerceptionModel project.
