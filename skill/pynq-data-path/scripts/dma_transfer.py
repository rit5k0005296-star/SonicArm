#!/usr/bin/env python3
"""Reusable AXI DMA transfer wrapper for PYNQ buffers and injectable test doubles."""
import time


class DmaTransferError(RuntimeError):
    pass


def _sync(buffer, direction):
    names = ("sync_to_device", "flush") if direction == "to_device" else ("sync_from_device", "invalidate")
    for name in names:
        method = getattr(buffer, name, None)
        if callable(method):
            method()
            return name
    if not getattr(buffer, "coherent", False):
        raise DmaTransferError("CACHE_SYNC_API_UNAVAILABLE:" + direction)
    return "coherent"


def _address(buffer):
    for name in ("device_address", "physical_address"):
        value = getattr(buffer, name, None)
        if isinstance(value, int):
            return value
    raise DmaTransferError("DEVICE_ADDRESS_UNAVAILABLE")


class DmaTransfer:
    def __init__(self, dma, alignment=1, timeout_s=10.0, poll_s=0.001):
        if alignment <= 0 or alignment & (alignment - 1):
            raise ValueError("alignment must be a power of two")
        self.dma = dma
        self.alignment = alignment
        self.timeout_s = float(timeout_s)
        self.poll_s = float(poll_s)

    def _check(self, buffer, nbytes):
        size = getattr(buffer, "nbytes", None)
        if not isinstance(size, int) or size <= 0:
            raise DmaTransferError("BUFFER_SIZE_UNAVAILABLE")
        count = size if nbytes is None else int(nbytes)
        if count <= 0 or count > size:
            raise DmaTransferError("INVALID_TRANSFER_LENGTH")
        if _address(buffer) % self.alignment:
            raise DmaTransferError("UNALIGNED_BUFFER_ADDRESS")
        return count

    def _wait(self, channel, label):
        deadline = time.monotonic() + self.timeout_s
        idle = getattr(channel, "idle", None)
        if isinstance(idle, bool):
            while not channel.idle:
                if time.monotonic() >= deadline:
                    raise DmaTransferError("TRANSFER_TIMEOUT:" + label)
                time.sleep(self.poll_s)
        else:
            channel.wait()

    def exchange(self, send_buffer, recv_buffer, nbytes=None):
        send = getattr(self.dma, "sendchannel", None)
        recv = getattr(self.dma, "recvchannel", None)
        if send is None or recv is None:
            raise DmaTransferError("DMA_CHANNEL_MISSING")
        send_count = self._check(send_buffer, nbytes)
        recv_count = self._check(recv_buffer, nbytes)
        count = min(send_count, recv_count)
        tx_sync = _sync(send_buffer, "to_device")
        recv.transfer(recv_buffer, nbytes=count)
        send.transfer(send_buffer, nbytes=count)
        self._wait(send, "send")
        self._wait(recv, "recv")
        rx_sync = _sync(recv_buffer, "from_device")
        return {"bytes": count, "tx_sync": tx_sync, "rx_sync": rx_sync}
