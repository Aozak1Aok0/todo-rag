"""从 Windows 凭据管理器读通用凭据（key 不落盘、不写进配置文件）。

默认目标名见 DEFAULT_TARGET，可用环境变量 CRED_TARGET 覆盖。
"""

import ctypes
import os
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
DEFAULT_TARGET = "WorkBuddy/DeepSeek"


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.windll.advapi32
_advapi32.CredReadW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.POINTER(CREDENTIAL)]
_advapi32.CredFree.restype = None


def read_credential(target: str) -> str:
    ptr = ctypes.POINTER(CREDENTIAL)()
    ok = _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr))
    if not ok:
        err = ctypes.get_last_error() or ctypes.GetLastError()
        raise OSError(err, f"读不到凭据 {target!r}（控制面板 → 凭据管理器 → Windows 凭据）")
    try:
        cred = ptr.contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return raw.decode("utf-16-le").rstrip("\x00")
    finally:
        _advapi32.CredFree(ptr)


def get_deepseek_key() -> str:
    """优先环境变量，其次 Windows 凭据管理器。"""
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    return read_credential(os.getenv("CRED_TARGET", DEFAULT_TARGET))


if __name__ == "__main__":
    k = get_deepseek_key()
    print(f"len={len(k)} prefix={k[:7]}…{k[-4:]}")