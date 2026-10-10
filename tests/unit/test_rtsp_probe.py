from __future__ import annotations

import pytest

from visitor_counter import rtsp_probe


class FakeRTSP:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, value):
        pass

    def sendall(self, request):
        self.requests.append(request.decode())

    def recv(self, size):
        return next(self.responses)


@pytest.mark.parametrize("code,expected", [(200, True), (404, False)])
def test_rtsp_port_and_profile_do_not_claim_video_frames(monkeypatch, code, expected):
    connection = FakeRTSP([f"RTSP/1.0 {code} Response\r\nContent-Length: 0\r\n\r\n".encode()])
    monkeypatch.setattr(rtsp_probe.socket, "create_connection", lambda *a, **k: connection)
    result = rtsp_probe.probe_rtsp_source("rtsp://192.168.1.20/Preview_01_sub")
    assert result.port_reachable
    assert result.sdp_available is expected
    if expected:
        assert "Videoframes noch unbestätigt" in result.detail


@pytest.mark.parametrize("code,expected", [(200, "authenticated"), (401, "rejected")])
def test_digest_login_is_distinguished_and_credentials_are_redacted(monkeypatch, code, expected):
    connection = FakeRTSP([
        b'RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Digest realm="camera", nonce="fixture"\r\nContent-Length: 0\r\n\r\n',
        f"RTSP/1.0 {code} Response\r\nContent-Length: 0\r\n\r\n".encode(),
    ])
    monkeypatch.setattr(rtsp_probe.socket, "create_connection", lambda *a, **k: connection)
    result = rtsp_probe.probe_rtsp_source("rtsp://fake:fixture-password@192.168.1.20/stream")
    assert result.authentication == expected
    assert "Authorization: Digest" in connection.requests[1]
    assert "fixture-password" not in " ".join(connection.requests)
    assert "fixture-password" not in repr(result)


def test_missing_rtsp_credentials_and_unreachable_port_are_distinct(monkeypatch):
    connection = FakeRTSP([b'RTSP/1.0 401 Unauthorized\r\nContent-Length: 0\r\n\r\n'])
    monkeypatch.setattr(rtsp_probe.socket, "create_connection", lambda *a, **k: connection)
    result = rtsp_probe.probe_rtsp_source("rtsp://192.168.1.20/stream")
    assert result.port_reachable and result.authentication == "required"

    def refused(*args, **kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(rtsp_probe.socket, "create_connection", refused)
    result = rtsp_probe.probe_rtsp_source("rtsp://192.168.1.20/stream")
    assert not result.port_reachable and result.authentication == "unknown"
