# GTA SA 1.0 US — External Aimbot + ESP (Python)

Target: Grand Theft Auto: San Andreas **v1.0 US** (`gta_sa.exe`), Windows.
Offsets are for 1.0 US only (gtamods "Memory Addresses (SA)").
Not for v1.01 / v2 / v3 (Steam) or the Definitive Edition.

## Install

```
pip install -r requirements.txt
```

## Run

1. Start the game (windowed or borderless recommended).
2. `python main.py`

## Controls

| Key | Action |
| --- | --- |
| F5 | toggle ESP |
| F6 | toggle aimbot |
| Hold Right Mouse | aim lock (on foot, armed) |
| END | exit |

## How it works

- **Memory**: pymem reads the ped pool (`0xB74490` usage info, contiguous
  `0x7C4`-stride ped array, flags byte-map) and the local player (`0xB6F5F0`).
- **ESP**: the camera world matrix is auto-detected every frame — the first
  orthonormal 4x4 matrix within 150 m of the player inside the CCamera block
  (`0xB6F028`) — inverted to a view matrix, then a perspective projection
  (vertical FOV, default 70) maps peds to screen space. Boxes, health bars,
  distance labels, snaplines, target highlight, FOV circle.
- **Aimbot**: while RMB is held, the ped nearest the crosshair (inside
  `AIM_FOV_PX` and `AIM_MAX_DIST`) is selected and the player's heading
  (`CPed+0x558` / `+0x55C`) is written to face it. The game's own auto-aim
  snaps the shot — enable **Auto Aim** in Settings > Controls.

## Tuning

- `FOV_DEG` in `main.py` — projection vertical FOV (GTA SA default 70).
  Raise/lower if boxes sit high or low.
- `AIM_FOV_PX`, `AIM_MAX_DIST`, `SHOW_LINES` in `main.py`.
- Ped box height is hardcoded to ~1.8 m in `esp.py` (`_box_rect`).

## Notes

- Single-player only. External reads/writes; no injection.
- If ESP draws nothing: check the game version is 1.0 US, and that the
  camera matrix detection finds a candidate (cutscenes move the camera far
  from the player — ESP pauses there by design).
