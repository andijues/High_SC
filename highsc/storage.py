from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import threading
from ctypes import wintypes
from pathlib import Path

ROOT = Path(os.environ.get("HIGHSC_ROOT", Path(__file__).resolve().parents[1])).resolve()
DATA = Path(os.environ.get("HIGHSC_DATA_DIR", ROOT / "data")).resolve()
PAPERS = DATA / "papers"
LOCK = threading.RLock()


def atomic_json(path: Path, obj):
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def read_json(path: Path, default=None):
    with LOCK:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))


def paper_dir(pid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", pid):
        raise ValueError("论文编号无效")
    p = PAPERS / pid
    if not p.is_dir():
        raise FileNotFoundError("论文不存在")
    return p


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt=False) -> bytes:
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "High_SC API key", None, None, None, 1, ctypes.byref(dst))
    if not ok:
        raise OSError("Windows 无法读取或保存 API 密钥，请重新填写密钥")
    try:
        return ctypes.string_at(dst.data, dst.size)
    finally:
        ctypes.windll.kernel32.LocalFree(dst.data)


def protect(secret: str) -> str:
    if not secret:
        return ""
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(secret.encode())).decode()
    return "local:" + base64.b64encode(secret.encode()).decode()


def unprotect(secret: str) -> str:
    if not secret:
        return ""
    scheme, encoded = secret.split(":", 1)
    raw = base64.b64decode(encoded)
    if scheme == "dpapi":
        if os.name != "nt":
            raise ValueError("此密钥由 Windows 账户加密，请在本机重新配置")
        raw = _dpapi(raw, decrypt=True)
    return raw.decode()


DEFAULT_CONFIG = {
    "base_url": "", "model": "", "api_style": "chat", "timeout": 180,
    "max_tokens": 8192, "batch_size": 4, "context_chars": 48000,
    "retries": 2, "json_mode": False, "send_temperature": False,
    "temperature": 0.2, "extra_body": {}, "proxy": "", "api_key_protected": "",
    "codex_path": "", "codex_effort": "xhigh",
    "auth_mode": "auto", "endpoint_mode": "auto", "token_field": "auto",
    "extra_headers_protected": "",
}


def load_config(public=False):
    c = {**DEFAULT_CONFIG, **read_json(DATA / "settings.json", {})}
    if public:
        c["has_api_key"] = bool(c.pop("api_key_protected", ""))
        c["has_extra_headers"] = bool(c.pop("extra_headers_protected", ""))
    else:
        c["api_key"] = unprotect(c.pop("api_key_protected", ""))
        c["extra_headers"] = json.loads(unprotect(c.pop("extra_headers_protected", "")) or "{}")
    return c


def save_config(values: dict):
    stored = {**DEFAULT_CONFIG, **read_json(DATA / "settings.json", {})}
    for k in DEFAULT_CONFIG:
        if k not in {"api_key_protected", "extra_headers_protected"} and k in values:
            stored[k] = values[k]
    if values.get("clear_api_key"):
        stored["api_key_protected"] = ""
    elif values.get("api_key"):
        stored["api_key_protected"] = protect(values["api_key"].strip())
    if values.get("clear_extra_headers"):
        stored["extra_headers_protected"] = ""
    elif values.get("extra_headers") is not None:
        stored["extra_headers_protected"] = protect(json.dumps(values["extra_headers"])) if values["extra_headers"] else ""
    atomic_json(DATA / "settings.json", stored)
    if os.name != "nt":
        os.chmod(DATA / "settings.json", 0o600)
    return load_config(public=True)
