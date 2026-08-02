from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
from pathlib import Path
from .paths import user_config_dir


class CredentialError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]




def _configure_dpapi() -> None:
    if os.name != "nt":
        return
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wt.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wt.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p


_configure_dpapi()

def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _dpapi_encrypt(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("DPAPI is available on Windows only")
    in_blob, keepalive = _blob(data)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), ctypes.c_wchar_p("AbrarStudio"), None, None, None, 0x1,
        ctypes.byref(out_blob),
    ):
        raise CredentialError("Windows DPAPI encryption failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_decrypt(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("DPAPI is available on Windows only")
    in_blob, keepalive = _blob(data)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0x1,
        ctypes.byref(out_blob),
    ):
        raise CredentialError("Windows DPAPI decryption failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class CredentialStore:
    """Stores the Gemini API key encrypted with Windows DPAPI.

    On non-Windows systems, keys are read from GEMINI_API_KEY and are never
    persisted. This keeps test and development systems from writing plaintext.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_config_dir() / "credentials.json")

    def set_api_key(self, key: str) -> None:
        key = key.strip()
        if len(key) < 20:
            raise CredentialError("The API key appears incomplete")
        if os.name != "nt":
            raise CredentialError("Secure key storage is enabled only in the Windows app")
        encrypted = _dpapi_encrypt(key.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": "windows-dpapi-v1", "ciphertext": base64.b64encode(encrypted).decode("ascii")}
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def get_api_key(self) -> str | None:
        env = os.getenv("GEMINI_API_KEY")
        if env:
            return env.strip()
        if not self.path.exists() or os.name != "nt":
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("format") != "windows-dpapi-v1":
            raise CredentialError("Unknown credential format")
        encrypted = base64.b64decode(payload["ciphertext"])
        return _dpapi_decrypt(encrypted).decode("utf-8")

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
