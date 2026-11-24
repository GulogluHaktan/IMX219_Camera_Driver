#!/bin/bash
# Build nv_imx219.ko with the custom wide modes ON THE ORIN (L4T R39.2.1, kernel 6.8.12-1021-tegra) and put it + the overlay in ~/imx219_backup.
# Install afterwards with:  bash kamera_mod.sh ham      (back to stock: bash kamera_mod.sh argus)
set -e
cd "$(dirname "$0")/i2c"
make -C /lib/modules/$(uname -r)/build M=$PWD KBUILD_EXTRA_SYMBOLS=/usr/src/nvidia/nvidia-public/Module.symvers modules
mkdir -p ~/imx219_backup
[ -f ~/imx219_backup/nv_imx219.ko.orig ] || cp /lib/modules/$(uname -r)/updates/drivers/media/i2c/nv_imx219.ko ~/imx219_backup/nv_imx219.ko.orig
[ -f ~/imx219_backup/imx219-dual.dtbo.orig ] || cp /boot/tegra234-p3767-camera-p3768-imx219-dual.dtbo ~/imx219_backup/imx219-dual.dtbo.orig
cp nv_imx219.ko ~/imx219_backup/nv_imx219.ko.wide_final
python3 ../make_overlay.py ~/imx219_backup/imx219-dual.dtbo.orig ~/imx219_backup/ab.dtbo
echo "built: ~/imx219_backup/nv_imx219.ko.wide_final + ab.dtbo  ->  bash kamera_mod.sh ham"
