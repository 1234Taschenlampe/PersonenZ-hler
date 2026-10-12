from __future__ import annotations

from pathlib import Path
import socket
import ssl
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
import pytest

from visitor_counter.tls_setup import create_lan_tls, repair_ca_usage


def strict_handshake(files: dict[str, Path]) -> None:
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(files["certificate"], files["private_key"])
    client_context = ssl.create_default_context(cafile=str(files["ca"]))
    client_context.verify_flags |= ssl.VERIFY_X509_STRICT
    errors = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(5)
        def serve():
            try:
                connection, _ = listener.accept()
                with server_context.wrap_socket(connection, server_side=True) as wrapped:
                    wrapped.sendall(b"verified")
            except Exception as exc:
                errors.append(exc)
        worker = Thread(target=serve)
        worker.start()
        try:
            with socket.create_connection(listener.getsockname(), timeout=5) as connection:
                with client_context.wrap_socket(connection, server_hostname="counter.local") as wrapped:
                    assert wrapped.recv(20) == b"verified"
        finally:
            worker.join(timeout=6)
        assert not worker.is_alive() and not errors


def test_ca_server_san_and_strict_tls_verification(tmp_path):
    files = create_lan_tls(tmp_path / "tls", "counter.local", ["127.0.0.1", "::1"])
    ca = x509.load_pem_x509_certificate(files["ca"].read_bytes())
    usage = ca.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.critical and usage.value.key_cert_sign and usage.value.crl_sign
    strict_handshake(files)
    old = files["private_key"].read_bytes()
    with pytest.raises(ValueError):
        create_lan_tls(tmp_path / "tls", "counter.local", [])
    assert files["private_key"].read_bytes() == old


def test_repair_ca_preserves_existing_server_identity_and_never_overwrites(tmp_path):
    files = create_lan_tls(tmp_path / "tls", "counter.local", [])
    server_before = files["certificate"].read_bytes()
    ca_before = files["ca"].read_bytes()
    ca = x509.load_pem_x509_certificate(ca_before)
    key = serialization.load_pem_private_key(files["ca_key"].read_bytes(), password=None)
    builder = (x509.CertificateBuilder().subject_name(ca.subject).issuer_name(ca.issuer)
               .public_key(ca.public_key()).serial_number(ca.serial_number)
               .not_valid_before(ca.not_valid_before_utc).not_valid_after(ca.not_valid_after_utc))
    for extension in ca.extensions:
        if not isinstance(extension.value, x509.KeyUsage):
            builder = builder.add_extension(extension.value, extension.critical)
    legacy_ca = tmp_path / "legacy-ca.crt"
    legacy_ca.write_bytes(builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM))
    repaired = tmp_path / "strict.crt"
    repair_ca_usage(legacy_ca, files["ca_key"], repaired)
    strict_handshake(dict(files, ca=repaired))
    assert files["certificate"].read_bytes() == server_before
    assert files["ca"].read_bytes() == ca_before
    with pytest.raises(FileExistsError):
        repair_ca_usage(files["ca"], files["ca_key"], repaired)
