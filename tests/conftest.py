"""Pytest compatibility shims for the local Windows/Python 3.14 setup."""
from __future__ import annotations

import os


if os.name == "nt":
    _ORIGINAL_MKDIR = os.mkdir

    def _mkdir_without_private_acl(path, mode=0o777, *, dir_fd=None):
        # Python 3.14 honors POSIX-ish 0o700 on Windows; in this OneDrive
        # workspace that creates directories the current process cannot scan.
        if mode == 0o700:
            mode = 0o777
        if dir_fd is None:
            return _ORIGINAL_MKDIR(path, mode)
        return _ORIGINAL_MKDIR(path, mode, dir_fd=dir_fd)

    os.mkdir = _mkdir_without_private_acl
