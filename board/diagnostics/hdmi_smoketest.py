#!/usr/bin/env python3
"""FPGA-10 HDMI OUT smoke test.

Loads the matched BIT/HWH pair, configures 1280x720 RGB output, and displays
color bars. This validates the PL HDMI/VDMA data path only; it does not claim
that the web UI or USB touch path is integrated.
"""

from pathlib import Path
import signal
import time

import numpy as np
from pynq import DefaultIP, Overlay
from pynq.lib.video import PIXEL_RGB, VideoMode
from pynq.lib.video.dma import AxiVDMA
import pynq.lib._video as _video


ROOT = Path(__file__).resolve().parent
BIT = ROOT / "fpga10_audio_hdmi.bit"


def main():
    overlay = Overlay(str(BIT), download=True)

    # PYNQ-Z2 HDMI OUT uses R19 as a source-side HPD/enable signal.  The
    # FPGA-10 block design exposes it through an AXI GPIO configured as an
    # output, so it must be asserted after every Overlay download.
    hpd = overlay.hdmi_out_hpd_gpio
    hpd.write(0x04, 0x00000000)  # channel 1 direction: output
    hpd.write(0x00, 0x00000001)  # assert HDMI OUT HPD/enable
    time.sleep(0.2)

    mode = VideoMode(1280, 720, 24, fps=60)
    # Use the same compiled PYNQ 3.0.1 display controller as the official
    # HDMIOutFrontend, but construct it directly because FPGA-10 keeps the
    # VTC and dynamic-clock IP at the top level instead of a named hierarchy.
    display = _video._display(
        overlay.ip_dict["vtc_out_0"]["phys_addr"],
        overlay.ip_dict["axi_dynclk_0"]["phys_addr"],
        1,
    )
    # Use the synchronous channel directly. Attempting to instantiate the
    # normal PYNQ driver first can leave a partially constructed driver after
    # PYNQ 3.0.1 fails to expose mm2s_introut; avoid that path entirely during
    # the physical HDMI smoke test.
    vdma_description = overlay.ip_dict["axi_vdma_0"]
    vdma_ip = DefaultIP(vdma_description)
    vdma_ip.framecount = int(vdma_description["parameters"]["C_NUM_FSTORES"])
    writechannel = AxiVDMA.MM2SChannel(
        vdma_ip,
        interrupt=None,
        memory=overlay.device.default_memory,
    )
    driver_mode = "synchronous-direct"

    overlay.color_convert_0.colorspace = PIXEL_RGB.out_color
    overlay.pixel_unpack_0.bits_per_pixel = 24
    display.mode(2)  # PYNQ output-mode index 2 = 1280x720
    writechannel.mode = mode
    display.start()
    time.sleep(0.2)
    writechannel.start()

    frame = writechannel.newframe()
    colors = np.array(
        [
            [255, 255, 255],
            [255, 255, 0],
            [0, 255, 255],
            [0, 255, 0],
            [255, 0, 255],
            [255, 0, 0],
            [0, 0, 255],
            [0, 0, 0],
        ],
        dtype=np.uint8,
    )
    width = mode.width // len(colors)
    for index, color in enumerate(colors):
        start = index * width
        end = mode.width if index == len(colors) - 1 else (index + 1) * width
        frame[:, start:end, :] = color
    frame.flush()
    writechannel.setframe(frame)
    time.sleep(0.2)
    print(
        "HDMI_DIAG "
        f"hpd_data=0x{hpd.read(0x00):08x} "
        f"hpd_tri=0x{hpd.read(0x04):08x} "
        f"vdma_cr=0x{vdma_ip.read(0x00):08x} "
        f"vdma_sr=0x{vdma_ip.read(0x04):08x} "
        f"park=0x{vdma_ip.read(0x28):08x} "
        f"vsize={vdma_ip.read(0x50)} "
        f"hsize={vdma_ip.read(0x54)} "
        f"stride=0x{vdma_ip.read(0x58):08x}"
    )
    print(
        "HDMI_SMOKETEST_RUNNING 1280x720 RGB color bars; "
        f"driver={driver_mode}; press Ctrl-C to stop"
    )
    def request_stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        writechannel.stop()
        display.stop()


if __name__ == "__main__":
    main()
