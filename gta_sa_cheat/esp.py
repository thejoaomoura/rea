# language: Python, file: esp.py, runtime: Windows, deps: pygame, pywin32

import pygame
import win32api
import win32con
import win32gui
import win32process

from camera import world_to_screen

COLOR_KEY = (0, 0, 0)
BOX_COLOR = (255, 60, 60)
TARGET_COLOR = (80, 255, 255)
LINE_COLOR = (120, 30, 30)
FOV_COLOR = (70, 70, 70)
TEXT_COLOR = (235, 235, 235)


def find_game_hwnd(pid):
    """First visible, titled top-level window owned by the game process."""
    found = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                found.append(hwnd)

    win32gui.EnumWindows(callback, None)
    for hwnd in found:
        if win32gui.GetWindowText(hwnd):
            return hwnd
    return None


class Overlay:
    """Click-through, always-on-top, colorkey-transparent pygame window
    positioned over the game's client area."""

    def __init__(self, pid):
        self.pid = pid
        self.game_hwnd = None
        self.hwnd = None
        self.screen = None
        self.font = None
        self.size = (0, 0)
        pygame.init()
        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 11, bold=True)

    def _create(self, w, h):
        self.screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
        self.hwnd = pygame.display.get_wm_info()["window"]
        style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            self.hwnd, win32con.GWL_EXSTYLE,
            style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
        )
        win32gui.SetLayeredWindowAttributes(
            self.hwnd, win32api.RGB(*COLOR_KEY), 0, win32con.LWA_COLORKEY)
        self.size = (w, h)

    def position(self, x, y, w, h):
        if w <= 0 or h <= 0:
            return
        if self.screen is None or self.size != (w, h):
            self._create(w, h)
        win32gui.SetWindowPos(
            self.hwnd, win32con.HWND_TOPMOST, x, y, w, h,
            win32con.SWP_NOACTIVATE)

    def clear(self):
        if self.screen is not None:
            self.screen.fill(COLOR_KEY)
            pygame.display.flip()

    def _box_rect(self, ped, view, fov, right):
        rx, ry, rz = right
        pts = []
        for dz, side in ((-0.10, -0.45), (-0.10, 0.45), (1.70, -0.45), (1.70, 0.45)):
            p = world_to_screen((ped.x + rx * side, ped.y + ry * side, ped.z + dz),
                                view, fov, self.size[0], self.size[1])
            if p is None:
                return None
            pts.append(p)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def draw(self, peds, target, fov_radius, show_lines, fov_deg, right):
        w, h = self.size
        self.screen.fill(COLOR_KEY)
        cx, cy = w / 2.0, h / 2.0

        pygame.draw.circle(self.screen, FOV_COLOR, (int(cx), int(cy)), fov_radius, 1)
        pygame.draw.line(self.screen, TEXT_COLOR, (int(cx) - 4, int(cy)), (int(cx) + 4, int(cy)))
        pygame.draw.line(self.screen, TEXT_COLOR, (int(cx), int(cy) - 4), (int(cx), int(cy) + 4))

        for ped in peds:
            if ped.screen is None:
                continue
            rect = self._box_rect(ped, self._view, fov_deg, right)
            if rect is None:
                continue
            bx, by, bx2, by2 = rect
            is_target = target is not None and ped.address == target.address
            color = TARGET_COLOR if is_target else BOX_COLOR
            width = 2 if is_target else 1

            if show_lines:
                pygame.draw.line(self.screen, LINE_COLOR, (cx, h), (ped.screen[0], ped.screen[1]), 1)
            pygame.draw.rect(self.screen, color, (bx, by, bx2 - bx, by2 - by), width)

            max_hp = ped.max_health if ped.max_health > 0 else 100.0
            pct = max(0.0, min(1.0, ped.health / max_hp))
            bar_h = by2 - by
            bar_color = (int(255 * (1.0 - pct)), int(255 * pct), 40)
            pygame.draw.rect(self.screen, bar_color, (bx - 6, by, 4, int(bar_h * pct)))
            pygame.draw.rect(self.screen, (20, 20, 20), (bx - 6, by, 4, bar_h), 1)

            label = f"{ped.dist:.0f}m"
            text = self.font.render(label, True, TEXT_COLOR)
            self.screen.blit(text, ((bx + bx2) / 2 - text.get_width() / 2, by2 + 3))

        pygame.display.flip()

    def set_view(self, view):
        self._view = view

    def close(self):
        pygame.quit()
