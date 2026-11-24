"""Build the camera overlay for the custom wide modes from the STOCK overlay (run on the Orin):
    python3 make_overlay.py /home/lovelace/imx219_backup/imx219-dual.dtbo.orig ab.dtbo
Appends mode5 (1640x864 @ 60), mode6 (1640x616 @ 84, duplicate slot), mode7 (1640x616 @ 84) to both sensor nodes, copied from mode4.
The driver's imx219_frmfmt table must list the same modes in the same order (imx219_mode_tbls.h)."""
import re, subprocess, sys
src, out = sys.argv[1], sys.argv[2]
s = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", src], capture_output=True, text=True, check=True).stdout
parts, pos = [], 0
for m in re.finditer(r"(\t+)mode4 \{.*?\n\1\};\n", s, re.S):
    blk = m.group(0); new = ""
    for k, h, f in ((5, 864, 60), (6, 616, 84), (7, 616, 84)):
        b = blk.replace("mode4 {", "mode%d {" % k, 1)
        b = re.sub(r'active_w = "\d+"', 'active_w = "1640"', b); b = re.sub(r'active_h = "\d+"', 'active_h = "%d"' % h, b)
        b = re.sub(r'max_framerate = "\d+"', 'max_framerate = "%d000000"' % f, b); b = re.sub(r'default_framerate = "\d+"', 'default_framerate = "%d000000"' % f, b)
        new += b
    parts.append(s[pos:m.end()] + new); pos = m.end()
open(out + ".dts", "w").write("".join(parts) + s[pos:])
subprocess.run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", out, out + ".dts"], check=True, capture_output=True); print("wrote", out)
