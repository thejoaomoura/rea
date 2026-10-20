# language: Python, file: main.py, runtime: Windows, deps: pymem, pygame, pywin32
# GTA San Andreas 1.0 US - external aimbot + ESP.
# Offsets: gtamods "Memory Addresses (SA)" v1.0 US. Camera matrix auto-detected.

import math
import struct
from ctypes import windll

import pygame
import win32gui

from offsets import (
    GAME_PROCESS,
    PLAYER_PTR,
    PED_POOL,
    POOL_OBJECTS,
    POOL_FLAGS,
    POOL_MAX,
    PED_STRIDE,
    PED_MATRIX,
    MAT_POS,
    PED_HEALTH,
    PED_STATE,
    PED_ON_FOOT,
    PED_WEAPON,
)
from memory import Memory
from camera import (
    find_camera_matrix_offset,
    world_matrix_from_block,
    view_matrix_from_world,
    world_to_screen,
)
from entities import parse_peds
from esp import Overlay, find_game_hwnd
from aimbot import rmb_held, aim_at

# settings
AIM_FOV_PX = 120        # crosshair capture radius in pixels
AIM_MAX_DIST = 80.0     # meters
FOV_DEG = 70.0          # projection vertical FOV (GTA SA default = 70)
SHOW_LINES = True

VK_F5 = 0x74
VK_F6 = 0x75
VK_END = 0x23


def main():
    try:
        mem = Memory(GAME_PROCESS)
    except Exception as exc:
        print(f"[-] {GAME_PROCESS} not running: {exc}")
        return
    print(f"[+] attached to {GAME_PROCESS}, base 0x{mem.base:X}")

    try:
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    overlay = Overlay(mem.pm.process_id)
    esp_on = True
    aim_on = True
    prev_keys = {}
    consecutive_errors = 0
    clock = pygame.time.Clock()

    while True:
        # hotkeys (edge-detected)
        for vk in (VK_F5, VK_F6):
            down = bool(windll.user32.GetAsyncKeyState(vk) & 0x8000)
            was = prev_keys.get(vk, False)
            prev_keys[vk] = down
            if down and not was:
                if vk == VK_F5:
                    esp_on = not esp_on
                    print(f"[esp] {'ON' if esp_on else 'OFF'}")
                else:
                    aim_on = not aim_on
                    print(f"[aim] {'ON' if aim_on else 'OFF'}")
        if windll.user32.GetAsyncKeyState(VK_END) & 0x8000:
            break

        try:
            # game window
            if overlay.game_hwnd is None or not win32gui.IsWindow(overlay.game_hwnd):
                overlay.game_hwnd = find_game_hwnd(mem.pm.process_id)
            if overlay.game_hwnd is None:
                clock.tick(30)
                continue
            rect = win32gui.GetClientRect(overlay.game_hwnd)
            gx, gy = win32gui.ClientToScreen(overlay.game_hwnd, (rect[0], rect[1]))
            gw, gh = rect[2] - rect[0], rect[3] - rect[1]
            if gw <= 0 or gh <= 0:
                clock.tick(30)
                continue
            overlay.position(gx, gy, gw, gh)

            # local player
            player_addr = mem.read_int(mem.base + PLAYER_PTR)
            if not player_addr:
                clock.tick(30)
                continue
            matrix = mem.read_int(player_addr + PED_MATRIX)
            if not matrix:
                clock.tick(30)
                continue
            px, py, pz = struct.unpack("<3f", mem.read(matrix + MAT_POS, 12))
            health = mem.read_float(player_addr + PED_HEALTH)
            state = mem.read_int(player_addr + PED_STATE)
            on_foot = mem.read_int(player_addr + PED_ON_FOOT)
            weapon = mem.read_int(player_addr + PED_WEAPON)

            # camera
            cam_off, block = find_camera_matrix_offset(mem, (px, py, pz))
            view = None
            right = None
            if cam_off is not None:
                wmat = world_matrix_from_block(block, cam_off)
                view = view_matrix_from_world(wmat)
                right = (wmat[0], wmat[1], wmat[2])
                overlay.set_view(view)

            # ped pool
            objects = mem.read_int(mem.base + PED_POOL + POOL_OBJECTS)
            flags_ptr = mem.read_int(mem.base + PED_POOL + POOL_FLAGS)
            max_peds = mem.read_int(mem.base + PED_POOL + POOL_MAX)
            if not objects or not flags_ptr or not (0 < max_peds <= 256):
                clock.tick(30)
                continue
            flags_buf = mem.read(flags_ptr, max_peds)
            pool_buf = mem.read(objects, max_peds * PED_STRIDE)
            peds = parse_peds(pool_buf, flags_buf, max_peds, objects, player_addr)

            # world-to-screen + distance
            for ped in peds:
                if view is None:
                    ped.screen = None
                    continue
                ped.screen = world_to_screen((ped.x, ped.y, ped.z), view, FOV_DEG, gw, gh)
                ped.dist = math.sqrt((ped.x - px) ** 2 + (ped.y - py) ** 2 + (ped.z - pz) ** 2)

            # aimbot: nearest ped to the crosshair inside the FOV radius
            target = None
            if (aim_on and rmb_held() and view is not None
                    and on_foot == 3 and health > 0.0
                    and state not in (55, 63) and weapon != 0):
                best = AIM_FOV_PX * AIM_FOV_PX
                for ped in peds:
                    if ped.screen is None or ped.dist > AIM_MAX_DIST:
                        continue
                    dx = ped.screen[0] - gw / 2.0
                    dy = ped.screen[1] - gh / 2.0
                    d2 = dx * dx + dy * dy
                    if d2 < best:
                        best = d2
                        target = ped
                if target is not None:
                    aim_at(mem, player_addr, px, py, target)

            # esp
            if esp_on and view is not None:
                overlay.draw(peds, target, AIM_FOV_PX, SHOW_LINES, FOV_DEG, right)
            else:
                overlay.clear()

            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            if consecutive_errors > 30:
                print("[-] game closed or memory unreadable, exiting")
                break

        clock.tick(120)

    overlay.close()
    mem.close()
    print("[+] exited")


if __name__ == "__main__":
    main()
