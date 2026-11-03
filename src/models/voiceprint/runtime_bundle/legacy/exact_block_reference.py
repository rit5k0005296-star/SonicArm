"""Exact integer oracle using bounded FP32 dot products, not approximate inference.

Each product has magnitude <=128*255=32640. A block contains <=128
terms, so every partial sum is an exactly representable FP32 integer:
sum(abs(products))<=4177920<2**24. Blocks and bias are accumulated in
INT64. Requantization retains the original integer ties-to-even rule.
CPU NumPy/BLAS only; no model, weights, multiplier, or FPGA changes.
"""
import numpy as np


def integer_pointwise(layer, params, x, debug=False):
    ci = int(layer['cin']); co = int(layer['cout']); zp = int(layer['input_zp'])
    if x.dtype != np.int8 or x.ndim != 3 or x.shape[:2] != (1, ci) or x.shape[2] < 1:
        raise ValueError('Expected live INT8 [1,C,T] boundary')
    weights = params['weights']; bias = params['bias']; mult = params['multiplier']
    if not (-128 <= zp <= 127 and weights.dtype == np.int8 and weights.shape == (co, ci)
            and bias.dtype == np.int32 and bias.shape == (co,)
            and mult.dtype == np.uint32 and mult.shape == (co,)):
        raise ValueError('Integer oracle parameter contract mismatch')
    acc = np.broadcast_to(bias.astype(np.int64)[:, None], (co, x.shape[2])).copy()
    for begin in range(0, ci, 128):
        w = np.ascontiguousarray(weights[:, begin:begin+128], dtype=np.float32)
        v = np.ascontiguousarray(x[0, begin:begin+128].astype(np.int16) - zp, dtype=np.float32)
        partial = w @ v
        if partial.dtype != np.float32:
            raise TypeError('FP32 dot contract changed')
        acc += partial.astype(np.int64)
    if np.any(acc > 2147483647) or np.any(acc < -2147483648):
        raise OverflowError('INT32 accumulator')
    product = acc * mult.astype(np.int64)[:, None]
    mag = np.abs(product); shift = int(layer['requant_shift']); whole = mag >> shift
    fraction = mag & ((1 << shift) - 1); half = 1 << (shift - 1)
    whole += (fraction > half) | ((fraction == half) & ((whole & 1) != 0))
    q = np.clip(np.where(product < 0, -whole, whole) + layer['output_zp'], -128, 127).astype(np.int8)[None]
    return q, acc.astype(np.int32)[None] if debug else None
