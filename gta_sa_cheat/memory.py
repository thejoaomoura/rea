# language: Python, file: memory.py, runtime: Windows, deps: pymem

import pymem
import pymem.process


class Memory:
    """Thin wrapper over pymem for the gta_sa.exe process."""

    def __init__(self, process_name):
        self.pm = pymem.Pymem(process_name)
        module = pymem.process.module_from_name(self.pm.process_handle, process_name)
        self.base = module.lpBaseOfDll

    def read(self, address, size):
        return self.pm.read_bytes(address, size)

    def read_int(self, address):
        return self.pm.read_int(address)

    def read_float(self, address):
        return self.pm.read_float(address)

    def write_float(self, address, value):
        self.pm.write_float(address, value)

    def close(self):
        self.pm.close_process()
