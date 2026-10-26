import hashlib
import io
import os
import zipfile

import pytest

from merge_gate import bun


def fake_release(monkeypatch, payload: bytes, sha256: str | None = None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{bun.ASSET}/bun", payload)
    data = buf.getvalue()
    monkeypatch.setattr(bun, "SHA256", sha256 or hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(bun.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(data))
    monkeypatch.setattr(bun.sys, "platform", "linux")
    monkeypatch.setattr(bun.platform, "machine", lambda: "x86_64")


def test_installs_an_executable_bun_from_a_verified_archive(tmp_path, monkeypatch):
    fake_release(monkeypatch, b"#!/bin/sh\n")
    path = bun.install(tmp_path)
    assert path.read_bytes() == b"#!/bin/sh\n" and os.access(path, os.X_OK)


def test_refuses_an_archive_with_another_checksum(tmp_path, monkeypatch):
    fake_release(monkeypatch, b"tampered", sha256="0" * 64)
    with pytest.raises(SystemExit):
        bun.install(tmp_path)
    assert not (tmp_path / bun.ASSET).exists()
