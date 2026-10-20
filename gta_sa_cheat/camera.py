# language: Python, file: camera.py, target: GTA SA 1.0 US camera (CCamera)

import math
import struct
from typing import Optional, Tuple

from offsets import CAMERA, CCAMERA_SIZE


def _unit(v, tol=0.02):
    return abs(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) - 1.0) <= tol


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def find_camera_matrix_offset(mem, player_pos):
    """Locate a camera world matrix inside the CCamera block.

    The block holds several 4x4 matrices (the CPlaceable base matrix, the live
    camera matrix, last frame's matrix, mirror matrices). Any of them works as
    a world->camera source after inversion, so we take the first candidate
    that is orthonormal and sits within 150 m of the player. Returns the
    offset of the matrix within the CCamera block, or None.
    """
    block = mem.read(mem.base + CAMERA, CCAMERA_SIZE)
    px, py, pz = player_pos
    for off in range(0, CCAMERA_SIZE - 0x40, 4):
        tx, ty, tz = struct.unpack_from("<3f", block, off + 0x30)
        dx, dy, dz = tx - px, ty - py, tz - pz
        if dx * dx + dy * dy + dz * dz > 150.0 * 150.0 or abs(dz) > 40.0:
            continue
        r0 = struct.unpack_from("<3f", block, off + 0x00)
        r1 = struct.unpack_from("<3f", block, off + 0x10)
        r2 = struct.unpack_from("<3f", block, off + 0x20)
        if not (_unit(r0) and _unit(r1) and _unit(r2)):
            continue
        if abs(_dot(r0, r1)) > 0.02 or abs(_dot(r0, r2)) > 0.02 or abs(_dot(r1, r2)) > 0.02:
            continue
        return off, block
    return None, block


def world_matrix_from_block(block, off):
    return list(struct.unpack_from("<16f", block, off))


def view_matrix_from_world(w):
    """Invert an affine [R|t] world matrix: V = [R^T | -R^T t]."""
    return [
        w[0], w[4], w[8], 0.0,
        w[1], w[5], w[9], 0.0,
        w[2], w[6], w[10], 0.0,
        -(w[0] * w[12] + w[4] * w[13] + w[8] * w[14]),
        -(w[1] * w[12] + w[5] * w[13] + w[9] * w[14]),
        -(w[2] * w[12] + w[6] * w[13] + w[10] * w[14]),
        1.0,
    ]


def world_to_screen(p, view, fov_deg, width, height) -> Optional[Tuple[float, float]]:
    """Project a world point through the view matrix and a perspective
    projection. Returns (screen_x, screen_y) or None when off-screen/behind."""
    x, y, z = p
    cx = view[0] * x + view[4] * y + view[8] * z + view[12]
    cy = view[1] * x + view[5] * y + view[9] * z + view[13]
    cz = view[2] * x + view[6] * y + view[10] * z + view[14]
    if cz >= -0.1:
        return None
    tan_half = math.tan(math.radians(fov_deg) * 0.5)
    aspect = width / height
    ndc_x = (cx / -cz) / (tan_half * aspect)
    ndc_y = (cy / -cz) / tan_half
    if abs(ndc_x) > 1.0 or abs(ndc_y) > 1.0:
        return None
    sx = (ndc_x + 1.0) * 0.5 * width
    sy = (1.0 - ndc_y) * 0.5 * height
    return sx, sy
