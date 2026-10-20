# language: Python, file: aimbot.py, target: GTA SA 1.0 US

import math
from ctypes import windll

from offsets import PED_ROT_Z, PED_ROT_Z_TARGET

VK_RBUTTON = 0x02


def rmb_held():
    return bool(windll.user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)


def aim_at(mem, player_addr, px, py, target):
    """Rotate the local player to face the target.

    GTA SA stores the ped heading as rotation about Z. The ped's forward
    vector is local +Y, so forward(theta) = (-sin(theta), cos(theta)) and
    theta = atan2(-dx, dy). Writing both the current and target rotation
    makes the game's auto-aim snap the shot once the crosshair is on target.
    """
    dx = target.x - px
    dy = target.y - py
    rot = math.atan2(-dx, dy)
    mem.write_float(player_addr + PED_ROT_Z, rot)
    mem.write_float(player_addr + PED_ROT_Z_TARGET, rot)
