"""Proof of Work (POW) token generation for ChatGPT web reverse."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import pybase64

NAVIGATOR_KEYS = [
    "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
    "storage−[object StorageManager]",
    "locks−[object LockManager]",
    "appCodeName−Mozilla",
    "permissions−[object Permissions]",
    "webdriver−false",
    "vendor−Google Inc.",
    "mediaDevices−[object MediaDevices]",
    "cookieEnabled−true",
    "product−Gecko",
    "appName−Netscape",
    "language−zh-CN",
    "hardwareConcurrency−32",
    "pdfViewerEnabled−true",
    "bluetooth−[object Bluetooth]",
]

DOCUMENT_KEYS = ["_reactListeningo743lnnpvdg", "location"]

WINDOW_KEYS = [
    "window", "self", "document", "name", "location", "history",
    "navigator", "origin", "screen", "innerWidth", "innerHeight",
    "scrollX", "pageXOffset", "scrollY", "pageYOffset",
    "screenX", "screenY", "outerWidth", "outerHeight", "devicePixelRatio",
    "clientInformation", "screenLeft", "screenTop",
    "styleMedia", "onsearch", "isSecureContext", "trustedTypes",
    "performance", "crypto", "indexedDB", "sessionStorage", "localStorage",
    "crossOriginIsolated", "scheduler", "alert", "atob", "blur", "btoa",
    "fetch", "focus", "getComputedStyle", "getSelection", "matchMedia",
    "open", "postMessage", "print", "prompt", "queueMicrotask",
    "requestAnimationFrame", "setInterval", "setTimeout", "stop",
    "structuredClone", "chrome", "caches", "cookieStore",
    "speechSynthesis", "webpackChunk_N_E", "__NEXT_DATA__", "next",
]

CORES = [8, 16, 24, 32]
TIME_LAYOUT = "%a %b %d %Y %H:%M:%S"

_cached_scripts: list[str] = []
_cached_dpl: str = ""
_cached_time: float = 0


class ScriptSrcParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        global _cached_scripts, _cached_dpl, _cached_time
        if tag == "script":
            attrs_dict = dict(attrs)
            if "src" in attrs_dict:
                src = attrs_dict["src"]
                _cached_scripts.append(src)
                match = re.search(r"c/[^/]*/_", src)
                if match:
                    _cached_dpl = match.group(0)
                    _cached_time = time.time()


def _get_parse_time() -> str:
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.strftime(TIME_LAYOUT) + " GMT-0500 (Eastern Standard Time)"


def get_config(user_agent: str) -> list:
    return [
        random.choice([1920 + 1080, 2560 + 1440, 1920 + 1200, 2560 + 1600]),
        _get_parse_time(),
        4294705152,
        0,
        user_agent,
        random.choice(_cached_scripts) if _cached_scripts else "",
        _cached_dpl,
        "en-US",
        "en-US,es-US,en,es",
        0,
        random.choice(NAVIGATOR_KEYS),
        random.choice(DOCUMENT_KEYS),
        random.choice(WINDOW_KEYS),
        time.perf_counter() * 1000,
        str(uuid.uuid4()),
        "",
        random.choice(CORES),
        time.time() * 1000 - (time.perf_counter() * 1000),
    ]


def _generate_answer(seed: str, diff: str, config: list) -> tuple[str, bool]:
    diff_len = len(diff)
    seed_encoded = seed.encode()
    static_part1 = (json.dumps(config[:3], separators=(",", ":"), ensure_ascii=False)[:-1] + ",").encode()
    static_part2 = ("," + json.dumps(config[4:9], separators=(",", ":"), ensure_ascii=False)[1:-1] + ",").encode()
    static_part3 = ("," + json.dumps(config[10:], separators=(",", ":"), ensure_ascii=False)[1:]).encode()
    target_diff = bytes.fromhex(diff)

    for i in range(500000):
        di = str(i).encode()
        dj = str(i >> 1).encode()
        final = static_part1 + di + static_part2 + dj + static_part3
        base_enc = pybase64.b64encode(final)
        h = hashlib.sha3_512(seed_encoded + base_enc).digest()
        if h[:diff_len] <= target_diff:
            return base_enc.decode(), True

    fallback = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + pybase64.b64encode(f'"{seed}"'.encode()).decode()
    return fallback, False


def get_answer_token(seed: str, diff: str, config: list) -> tuple[str, bool]:
    answer, solved = _generate_answer(seed, diff, config)
    return "gAAAAAB" + answer, solved


def get_requirements_token(config: list) -> str:
    req, _ = _generate_answer(format(random.random()), "0fffff", config)
    return "gAAAAAC" + req


async def fetch_dpl(host_url: str, headers: dict, client) -> bool:
    global _cached_scripts, _cached_dpl, _cached_time
    if time.time() - _cached_time < 15 * 60:
        return True
    _cached_scripts = []
    _cached_dpl = ""
    try:
        r = await client.get(f"{host_url}/", headers=headers, timeout=5)
        r.raise_for_status()
        parser = ScriptSrcParser()
        parser.feed(r.text)
        if not _cached_scripts:
            _cached_scripts.append(f"{host_url}/backend-api/sentinel/sdk.js")
        if not _cached_dpl:
            match = re.search(r'<html[^>]*data-build="([^"]*)"', r.text)
            if match:
                _cached_dpl = match.group(1)
                _cached_time = time.time()
            else:
                _cached_dpl = None
                _cached_time = time.time()
                return False
        return True
    except Exception:
        _cached_dpl = None
        _cached_time = time.time()
        return False
