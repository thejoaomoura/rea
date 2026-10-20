# language: Python, file: entities.py, target: GTA SA 1.0 US ped pool

import math
import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

from offsets import (
    PED_STRIDE,
    PED_MATRIX,
    MAT_POS,
    PED_HEALTH,
    PED_MAX_HEALTH,
    PED_ARMOR,
    PED_STATE,
    PED_ON_FOOT,
    PED_WEAPON,
    PED_ROT_Z,
)


@dataclass
class Ped:
    address: int
    x: float
    y: float
    z: float
    health: float
    max_health: float
    armor: float
    state: int
    on_foot: int
    weapon: int
    rotation: float
    screen: Optional[Tuple[float, float]] = None
    dist: float = 0.0


def _sane(x, y, z, health):
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return False
    if not (0.0 < health <= 10000.0):
        return False
    if abs(x) > 200000.0 or abs(y) > 200000.0:
        return False
    if not (-100.0 < z < 10000.0):
        return False
    return True


def parse_peds(pool_buf, flags_buf, max_peds, objects_base, player_addr):
    """Walk the contiguous ped pool and return valid, alive, non-player peds."""
    peds = []
    count = min(max_peds, len(flags_buf))
    for i in range(count):
        if flags_buf[i] & 1:  # free slot
            continue
        base = i * PED_STRIDE
        if base + PED_STRIDE > len(pool_buf):
            break
        x, y, z = struct.unpack_from("<3f", pool_buf, base + PED_MATRIX + MAT_POS)
        health, max_health, armor = struct.unpack_from("<3f", pool_buf, base + PED_HEALTH)
        if not _sane(x, y, z, health):
            continue
        state = struct.unpack_from("<i", pool_buf, base + PED_STATE)[0]
        on_foot = pool_buf[base + PED_ON_FOOT]
        weapon = struct.unpack_from("<i", pool_buf, base + PED_WEAPON)[0]
        rotation = struct.unpack_from("<f", pool_buf, base + PED_ROT_Z)[0]
        address = objects_base + base
        if address == player_addr:
            continue
        peds.append(Ped(address, x, y, z, health, max_health, armor,
                        state, on_foot, weapon, rotation))
    return peds
