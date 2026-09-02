from tracelens.proxy.capture import capture_body, sanitize_headers


def test_sanitize_headers_redacts_sensitive_values() -> None:
    headers = [("Authorization", "Bearer secret"), ("X-Request-Id", "request-123")]

    captured = sanitize_headers(headers)

    assert '"Authorization": "[REDACTED]"' in captured
    assert '"X-Request-Id": "request-123"' in captured


def test_capture_body_omits_binary_and_oversized_content() -> None:
    binary_headers = [("content-type", "image/png")]
    text_headers = [("content-type", "text/plain")]

    assert capture_body(binary_headers, b"binary", max_bytes=64) is None
    assert capture_body(text_headers, b"too long", max_bytes=3) is None


def test_capture_body_omits_encoded_content() -> None:
    headers = [("content-type", "application/json"), ("content-encoding", "gzip")]

    assert capture_body(headers, b"encoded bytes", max_bytes=64) is None
