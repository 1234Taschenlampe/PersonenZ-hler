from visitor_counter.diagnostics import redact_sensitive


def test_diagnostic_redaction_removes_nested_secrets_and_url_credentials() -> None:
    source = {
        "viewer_token": "sensitive-value",
        "camera": "rtsp://operator:camera-pass@example.invalid/live",
        "message": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": [{"private_key": "key material"}],
    }
    result = redact_sensitive(source)
    serialized = str(result)
    assert "sensitive-value" not in serialized
    assert "camera-pass" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "key material" not in serialized
    assert "<redacted>" in serialized
