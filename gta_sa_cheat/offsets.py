# language: Python, file: offsets.py
# target: GTA San Andreas 1.0 US (gta_sa.exe), Windows
# verified against gtamods "Memory Addresses (SA)" (v1.0 US) and
# plugin-sdk CCamera.h (layout-accurate). NOT for v1.01/v2/v3 or Definitive Edition.

GAME_PROCESS = "gta_sa.exe"
GAME_VERSION = "1.0 US"

# Static addresses (added to the gta_sa.exe module base)
PLAYER_PTR = 0xB6F5F0        # CPed* - local player ped
PED_POOL = 0xB74490          # CPool usage info: +0 objects array, +4 flags, +8 max, +12 count
CAMERA = 0xB6F028            # CCamera block start (CCamera : CPlaceable)

# CPool layout
POOL_OBJECTS = 0x00          # CPed* - base of the contiguous ped array
POOL_FLAGS = 0x04            # uint8* - in-use map, bit 0 set = free slot
POOL_MAX = 0x08              # int32 - max peds (140)

# Ped pool
PED_STRIDE = 0x7C4           # sizeof(CPed) - pool holds contiguous ped objects

# CPed offsets
PED_MATRIX = 0x14            # CMatrix* - position/rotation structure
PED_HEALTH = 0x540           # float
PED_MAX_HEALTH = 0x544       # float
PED_ARMOR = 0x548            # float
PED_STATE = 0x530            # int32 - 55 = wasted, 63 = busted
PED_ON_FOOT = 0x46C          # byte - 3 = on foot, 1 = in car
PED_WEAPON = 0x740           # int32 - current weapon id (0 = fist)
PED_ROT_Z = 0x558            # float - current heading
PED_ROT_Z_TARGET = 0x55C     # float - target heading

# CMatrix layout (PED_MATRIX +)
MAT_RIGHT = 0x00
MAT_UP = 0x10
MAT_FORWARD = 0x20
MAT_POS = 0x30

# CCamera
CCAMERA_SIZE = 0xD78
