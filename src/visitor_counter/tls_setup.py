"""Private LAN TLS assets with strict X.509 verification (Python 3.13)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _key_usage(ca: bool) -> x509.KeyUsage:
    return x509.KeyUsage(digital_signature=True, content_commitment=False,
                         key_encipherment=not ca, data_encipherment=False,
                         key_agreement=False, key_cert_sign=ca, crl_sign=ca,
                         encipher_only=None, decipher_only=None)


def create_lan_tls(directory: Path, hostname: str, addresses: list[str]) -> dict[str, Path]:
    if not hostname or any(c.isspace() for c in hostname) or "://" in hostname:
        raise ValueError("A DNS hostname without scheme is required")
    sans = [x509.DNSName(hostname), *(x509.IPAddress(ipaddress.ip_address(a)) for a in addresses)]
    # Refuse replacement of any existing private material; reruns are safe.
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or any(directory.iterdir()):
        raise ValueError("TLS output must be an empty, regular private directory")
    directory.chmod(0o700)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{hostname} local CA")])
    ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(_key_usage(True), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    server = (x509.CertificateBuilder()
              .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
              .issuer_name(subject).public_key(server_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
              .not_valid_after(now + timedelta(days=730))
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(_key_usage(False), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
              .add_extension(x509.SubjectAlternativeName(sans), critical=False)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
    files = {"ca": directory / "ca.crt", "ca_key": directory / "ca.key",
             "certificate": directory / "server.crt", "private_key": directory / "server.key"}
    for label, obj in (("ca", ca), ("certificate", server)):
        with files[label].open("xb") as stream:
            stream.write(obj.public_bytes(serialization.Encoding.PEM))
        files[label].chmod(0o600)
    for label, key in (("ca_key", ca_key), ("private_key", server_key)):
        with files[label].open("xb") as stream:
            stream.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
        files[label].chmod(0o600)
    return files


def repair_ca_usage(certificate: Path, private_key: Path, output: Path) -> None:
    """Reissue the same self-signed CA identity/key, without rotating server keys.

    Clients must explicitly import the new trust certificate. Never replace the
    original CA or regenerate tokens/pairing files as a side effect.
    """
    ca = x509.load_pem_x509_certificate(certificate.read_bytes())
    key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
    if ca.subject != ca.issuer or not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Only a self-signed CA can be repaired")
    if ca.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
        raise ValueError("CA key does not match certificate")
    builder = (x509.CertificateBuilder().subject_name(ca.subject).issuer_name(ca.issuer)
               .public_key(key.public_key()).serial_number(ca.serial_number)
               .not_valid_before(ca.not_valid_before_utc).not_valid_after(ca.not_valid_after_utc))
    for extension in ca.extensions:
        if not isinstance(extension.value, x509.KeyUsage):
            builder = builder.add_extension(extension.value, extension.critical)
    builder = builder.add_extension(_key_usage(True), critical=True)
    result = builder.sign(key, hashes.SHA256())
    with output.open("xb") as stream:
        stream.write(result.public_bytes(serialization.Encoding.PEM))
    output.chmod(0o600)
