#!/usr/bin/env python3
"""Reusable Overlay loading and verification wrapper with injectable backends."""
from pathlib import Path


class OverlayVerificationError(RuntimeError):
    pass


class OverlaySession:
    def __init__(self, bitfile, required_ips=(), overlay_factory=None):
        self.bitfile = str(Path(bitfile))
        self.required_ips = tuple(required_ips)
        self._factory = overlay_factory
        self.overlay = None

    def open(self, download=False):
        factory = self._factory
        if factory is None:
            from pynq import Overlay
            factory = Overlay
        self.overlay = factory(self.bitfile, download=download)
        self.verify()
        return self.overlay

    def verify(self):
        if self.overlay is None:
            raise OverlayVerificationError("OVERLAY_NOT_OPEN")
        ip_dict = getattr(self.overlay, "ip_dict", None)
        if not isinstance(ip_dict, dict):
            raise OverlayVerificationError("IP_DICT_UNAVAILABLE")
        missing = [name for name in self.required_ips if name not in ip_dict]
        if missing:
            raise OverlayVerificationError("REQUIRED_IP_MISSING:" + ",".join(missing))
        return {"bitfile": self.bitfile, "ip_count": len(ip_dict), "required_ips": list(self.required_ips)}

    def ip(self, name):
        if self.overlay is None:
            raise OverlayVerificationError("OVERLAY_NOT_OPEN")
        if name not in self.overlay.ip_dict:
            raise OverlayVerificationError("IP_NOT_FOUND:" + name)
        return getattr(self.overlay, name)

    def register_map(self, name):
        block = self.ip(name)
        register_map = getattr(block, "register_map", None)
        if register_map is None:
            raise OverlayVerificationError("REGISTER_MAP_UNAVAILABLE:" + name)
        return register_map
