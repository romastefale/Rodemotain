"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import ipaddress
import json
import os
import socket
import ssl
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit


class PolicyError(RuntimeError):
    """Falha previsível causada por uma regra da política."""


@dataclasses.dataclass(frozen=True)
class PolicyConfig:
    allowed_hosts: frozenset[str]
    allowed_schemes: frozenset[str] = frozenset({"https"})
    max_redirects: int = 5
    max_response_bytes: int = 10 * 1024 * 1024
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 20.0
    permit_overwrite: bool = False
    use_environment_proxy: bool = False
    permit_url_credentials: bool = False
    permit_non_public_ip: bool = False

    def validate(self) -> None:
        if not self.allowed_hosts:
            raise PolicyError("allowed_hosts não pode ser vazio")
        if self.allowed_schemes != frozenset({"https"}):
            raise PolicyError("somente HTTPS é permitido")
        if self.max_redirects < 0 or self.max_redirects > 10:
            raise PolicyError("max_redirects fora do intervalo permitido")
        if self.max_response_bytes <= 0:
            raise PolicyError("max_response_bytes deve ser positivo")
        if self.use_environment_proxy:
            raise PolicyError("proxies de ambiente são proibidos")
        if self.permit_url_credentials:
            raise PolicyError("credenciais na URL são proibidas")
        if self.permit_non_public_ip:
            raise PolicyError("IPs não públicos são proibidos")

Código descartado pela regra:
@dataclasses.dataclass(frozen=True)
class PolicyConfig:
    allowed_hosts: frozenset[str] = frozenset()
    use_environment_proxy: bool = True
    permit_url_credentials: bool = True
    permit_non_public_ip: bool = True
    permit_overwrite: bool = True

Diff das versões:
--- /mnt/data/politica_restritiva_execucao/politica_restritiva.py.before	2026-07-27 16:55:56.441805787 +0000
+++ /mnt/data/politica_restritiva_execucao/politica_restritiva.py	2026-07-27 16:55:56.441805787 +0000
@@ -0,0 +1,57 @@
+#!/usr/bin/env python3
+"""Cliente HTTP restritivo com auditoria local verificável.
+
+A política aplica bloqueio por padrão. Não registra credenciais, cookies,
+corpos integrais ou valores de parâmetros de consulta.
+"""
+
+from __future__ import annotations
+
+import argparse
+import dataclasses
+import hashlib
+import ipaddress
+import json
+import os
+import socket
+import ssl
+import sys
+import tempfile
+import time
+from pathlib import Path
+from typing import Iterable
+from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit
+
+
+class PolicyError(RuntimeError):
+    """Falha previsível causada por uma regra da política."""
+
+
+@dataclasses.dataclass(frozen=True)
+class PolicyConfig:
+    allowed_hosts: frozenset[str]
+    allowed_schemes: frozenset[str] = frozenset({"https"})
+    max_redirects: int = 5
+    max_response_bytes: int = 10 * 1024 * 1024
+    connect_timeout_seconds: float = 10.0
+    read_timeout_seconds: float = 20.0
+    permit_overwrite: bool = False
+    use_environment_proxy: bool = False
+    permit_url_credentials: bool = False
+    permit_non_public_ip: bool = False
+
+    def validate(self) -> None:
+        if not self.allowed_hosts:
+            raise PolicyError("allowed_hosts não pode ser vazio")
+        if self.allowed_schemes != frozenset({"https"}):
+            raise PolicyError("somente HTTPS é permitido")
+        if self.max_redirects < 0 or self.max_redirects > 10:
+            raise PolicyError("max_redirects fora do intervalo permitido")
+        if self.max_response_bytes <= 0:
+            raise PolicyError("max_response_bytes deve ser positivo")
+        if self.use_environment_proxy:
+            raise PolicyError("proxies de ambiente são proibidos")
+        if self.permit_url_credentials:
+            raise PolicyError("credenciais na URL são proibidas")
+        if self.permit_non_public_ip:
+            raise PolicyError("IPs não públicos são proibidos")


Código adotado:


def normalize_host(host: str) -> str:
    normalized = host.rstrip(".").lower()
    if not normalized or len(normalized) > 253:
        raise PolicyError("host inválido")
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise PolicyError("host deve estar em ASCII/punycode") from exc
    return normalized


def redact_url(raw_url: str) -> dict[str, object]:
    parts = urlsplit(raw_url)
    query_names = sorted({name for name, _ in parse_qsl(parts.query, keep_blank_values=True)})
    sanitized = urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
    return {
        "url_sanitized": sanitized,
        "query_parameter_names": query_names,
        "query_parameter_count": len(parse_qsl(parts.query, keep_blank_values=True)),
        "fragment_present": bool(parts.fragment),
        "credentials_present": parts.username is not None or parts.password is not None,
    }


def validate_url(raw_url: str, config: PolicyConfig) -> tuple[str, str, int]:
    parts = urlsplit(raw_url)
    if parts.scheme.lower() not in config.allowed_schemes:
        raise PolicyError("esquema de URL não permitido")
    if parts.username is not None or parts.password is not None:
        raise PolicyError("credenciais na URL são proibidas")
    if not parts.hostname:
        raise PolicyError("URL sem host")
    host = normalize_host(parts.hostname)
    allowed = {normalize_host(item) for item in config.allowed_hosts}
    if host not in allowed:
        raise PolicyError(f"host fora da allowlist: {host}")
    port = parts.port or 443
    if port != 443:
        raise PolicyError("somente a porta 443 é permitida")
    return raw_url, host, port


def classify_ip(value: str) -> dict[str, object]:
    ip = ipaddress.ip_address(value)
    return {
        "ip": str(ip),
        "version": ip.version,
        "is_global": ip.is_global,
        "is_private": ip.is_private,
        "is_loopback": ip.is_loopback,
        "is_link_local": ip.is_link_local,
        "is_multicast": ip.is_multicast,
        "is_reserved": ip.is_reserved,
        "is_unspecified": ip.is_unspecified,
    }


def resolve_public_ips(host: str, port: int) -> tuple[list[str], list[dict[str, object]]]:
    observations: list[dict[str, object]] = []
    approved: set[str] = set()
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PolicyError(f"falha de resolução DNS: {exc}") from exc
    for _, _, _, _, sockaddr in results:
        address = sockaddr[0]
        classification = classify_ip(address)
        classification["approved"] = bool(classification["is_global"])
        observations.append(classification)
        if classification["is_global"]:
            approved.add(address)
    if not approved:
        raise PolicyError("DNS não retornou IP público aprovado")
    return sorted(approved), observations


class HashChainJsonl:
    def __init__(self, path: Path, *, trail_name: str) -> None:
        self.path = path
        self.trail_name = trail_name
        self.previous_hash = "0" * 64
        self.sequence = 0
        self.sealed = False
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise PolicyError(f"trilha já existe: {path}")
        self._handle = path.open("x", encoding="utf-8", newline="\n")

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def append(self, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        if self.sealed:
            raise PolicyError("trilha selada não aceita novos eventos")
        self.sequence += 1
        event: dict[str, object] = {
            "trail": self.trail_name,
            "sequence": self.sequence,
            "time_ns": time.time_ns(),
            "event_type": event_type,
            "previous_hash": self.previous_hash,
            "payload": payload,
        }
        digest = hashlib.sha256(self._canonical(event)).hexdigest()
        event["event_hash"] = digest
        self._handle.write(self._canonical(event).decode("utf-8") + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.previous_hash = digest
        return event

    def seal(self, private_key_path: Path | None = None) -> dict[str, object]:
        if self.sealed:
            raise PolicyError("trilha já selada")
        payload: dict[str, object] = {"final_event_hash": self.previous_hash}
        if private_key_path is not None:
            try:
                from cryptography.hazmat.primitives import serialization
            except ImportError as exc:
                raise PolicyError("biblioteca cryptography indisponível") from exc
            key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
            signature = key.sign(bytes.fromhex(self.previous_hash))
            payload["signature_hex"] = signature.hex()
            payload["signature_algorithm"] = "key-defined; expected Ed25519"
        final_event = self.append("seal", payload)
        self.sealed = True
        self._handle.close()
        return final_event

Código descartado pela regra:
def validate_url(raw_url, config):
    # Aceita qualquer host implícito e credenciais incorporadas.
    return raw_url

def resolve_public_ips(host, port):
    # Registra IPs privados, locais e reservados como destinos aprovados.
    return [item[4][0] for item in socket.getaddrinfo(host, port)]

class AuditTrail:
    def append(self, event):
        event["credentials"] = os.environ.get("HTTP_PASSWORD")
        event["cookies"] = response.headers.get("Set-Cookie")
        event["body"] = response.content.decode(errors="replace")

Diff das versões:
--- /mnt/data/politica_restritiva_execucao/politica_restritiva.py.before2	2026-07-27 16:56:47.501806953 +0000
+++ /mnt/data/politica_restritiva_execucao/politica_restritiva.py	2026-07-27 16:56:47.501806953 +0000
@@ -55,3 +55,134 @@
             raise PolicyError("credenciais na URL são proibidas")
         if self.permit_non_public_ip:
             raise PolicyError("IPs não públicos são proibidos")
+
+
+def normalize_host(host: str) -> str:
+    normalized = host.rstrip(".").lower()
+    if not normalized or len(normalized) > 253:
+        raise PolicyError("host inválido")
+    try:
+        normalized.encode("ascii")
+    except UnicodeEncodeError as exc:
+        raise PolicyError("host deve estar em ASCII/punycode") from exc
+    return normalized
+
+
+def redact_url(raw_url: str) -> dict[str, object]:
+    parts = urlsplit(raw_url)
+    query_names = sorted({name for name, _ in parse_qsl(parts.query, keep_blank_values=True)})
+    sanitized = urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
+    return {
+        "url_sanitized": sanitized,
+        "query_parameter_names": query_names,
+        "query_parameter_count": len(parse_qsl(parts.query, keep_blank_values=True)),
+        "fragment_present": bool(parts.fragment),
+        "credentials_present": parts.username is not None or parts.password is not None,
+    }
+
+
+def validate_url(raw_url: str, config: PolicyConfig) -> tuple[str, str, int]:
+    parts = urlsplit(raw_url)
+    if parts.scheme.lower() not in config.allowed_schemes:
+        raise PolicyError("esquema de URL não permitido")
+    if parts.username is not None or parts.password is not None:
+        raise PolicyError("credenciais na URL são proibidas")
+    if not parts.hostname:
+        raise PolicyError("URL sem host")
+    host = normalize_host(parts.hostname)
+    allowed = {normalize_host(item) for item in config.allowed_hosts}
+    if host not in allowed:
+        raise PolicyError(f"host fora da allowlist: {host}")
+    port = parts.port or 443
+    if port != 443:
+        raise PolicyError("somente a porta 443 é permitida")
+    return raw_url, host, port
+
+
+def classify_ip(value: str) -> dict[str, object]:
+    ip = ipaddress.ip_address(value)
+    return {
+        "ip": str(ip),
+        "version": ip.version,
+        "is_global": ip.is_global,
+        "is_private": ip.is_private,
+        "is_loopback": ip.is_loopback,
+        "is_link_local": ip.is_link_local,
+        "is_multicast": ip.is_multicast,
+        "is_reserved": ip.is_reserved,
+        "is_unspecified": ip.is_unspecified,
+    }
+
+
+def resolve_public_ips(host: str, port: int) -> tuple[list[str], list[dict[str, object]]]:
+    observations: list[dict[str, object]] = []
+    approved: set[str] = set()
+    try:
+        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
+    except socket.gaierror as exc:
+        raise PolicyError(f"falha de resolução DNS: {exc}") from exc
+    for _, _, _, _, sockaddr in results:
+        address = sockaddr[0]
+        classification = classify_ip(address)
+        classification["approved"] = bool(classification["is_global"])
+        observations.append(classification)
+        if classification["is_global"]:
+            approved.add(address)
+    if not approved:
+        raise PolicyError("DNS não retornou IP público aprovado")
+    return sorted(approved), observations
+
+
+class HashChainJsonl:
+    def __init__(self, path: Path, *, trail_name: str) -> None:
+        self.path = path
+        self.trail_name = trail_name
+        self.previous_hash = "0" * 64
+        self.sequence = 0
+        self.sealed = False
+        path.parent.mkdir(parents=True, exist_ok=True)
+        if path.exists():
+            raise PolicyError(f"trilha já existe: {path}")
+        self._handle = path.open("x", encoding="utf-8", newline="\n")
+
+    @staticmethod
+    def _canonical(value: object) -> bytes:
+        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
+
+    def append(self, event_type: str, payload: dict[str, object]) -> dict[str, object]:
+        if self.sealed:
+            raise PolicyError("trilha selada não aceita novos eventos")
+        self.sequence += 1
+        event: dict[str, object] = {
+            "trail": self.trail_name,
+            "sequence": self.sequence,
+            "time_ns": time.time_ns(),
+            "event_type": event_type,
+            "previous_hash": self.previous_hash,
+            "payload": payload,
+        }
+        digest = hashlib.sha256(self._canonical(event)).hexdigest()
+        event["event_hash"] = digest
+        self._handle.write(self._canonical(event).decode("utf-8") + "\n")
+        self._handle.flush()
+        os.fsync(self._handle.fileno())
+        self.previous_hash = digest
+        return event
+
+    def seal(self, private_key_path: Path | None = None) -> dict[str, object]:
+        if self.sealed:
+            raise PolicyError("trilha já selada")
+        payload: dict[str, object] = {"final_event_hash": self.previous_hash}
+        if private_key_path is not None:
+            try:
+                from cryptography.hazmat.primitives import serialization
+            except ImportError as exc:
+                raise PolicyError("biblioteca cryptography indisponível") from exc
+            key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
+            signature = key.sign(bytes.fromhex(self.previous_hash))
+            payload["signature_hex"] = signature.hex()
+            payload["signature_algorithm"] = "key-defined; expected Ed25519"
+        final_event = self.append("seal", payload)
+        self.sealed = True
+        self._handle.close()
+        return final_event


Código adotado:


class ApprovedIPHTTPSConnection:
    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        self.host = host
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock: ssl.SSLSocket | None = None

    def connect(self) -> None:
        raw = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw, server_hostname=self.host)
        certificate = self.sock.getpeercert()
        ssl.match_hostname(certificate, self.host)

    def request(self, method: str, target: str, headers: dict[str, str]) -> None:
        if self.sock is None:
            raise PolicyError("conexão TLS não estabelecida")
        lines = [f"{method} {target} HTTP/1.1", f"Host: {self.host}"]
        for key, value in headers.items():
            if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
                raise PolicyError("cabeçalho HTTP inválido")
            lines.append(f"{key}: {value}")
        lines.extend(["Connection: close", "", ""])
        self.sock.sendall("\r\n".join(lines).encode("ascii"))

    def read_response(self, max_bytes: int) -> tuple[int, dict[str, str], bytes]:
        if self.sock is None:
            raise PolicyError("conexão TLS não estabelecida")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = self.sock.recv(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise PolicyError("resposta excede o limite configurado")
        raw = b"".join(chunks)
        header_blob, separator, body = raw.partition(b"\r\n\r\n")
        if not separator:
            raise PolicyError("resposta HTTP sem cabeçalho completo")
        lines = header_blob.split(b"\r\n")
        try:
            status = int(lines[0].split(b" ", 2)[1])
        except (IndexError, ValueError) as exc:
            raise PolicyError("linha de status HTTP inválida") from exc
        headers: dict[str, str] = {}
        for line in lines[1:]:
            name, sep, value = line.partition(b":")
            if not sep:
                continue
            headers[name.decode("ascii", "strict").lower()] = value.decode("latin-1").strip()
        if headers.get("transfer-encoding", "").lower() == "chunked":
            raise PolicyError("transferência chunked não suportada pelo transporte restritivo")
        if "content-length" in headers and int(headers["content-length"]) != len(body):
            raise PolicyError("Content-Length divergente")
        return status, headers, body

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def atomic_write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PolicyError(f"arquivo de saída já existe: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, path)
        temp_path.unlink()
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def fetch(
    initial_url: str,
    output_path: Path,
    config: PolicyConfig,
    audit: HashChainJsonl,
    security: HashChainJsonl,
) -> dict[str, object]:
    config.validate()
    current_url = initial_url
    visited: set[str] = set()
    for redirect_index in range(config.max_redirects + 1):
        _, host, port = validate_url(current_url, config)
        if current_url in visited:
            raise PolicyError("ciclo de redirecionamento detectado")
        visited.add(current_url)
        approved_ips, observations = resolve_public_ips(host, port)
        audit.append("dns_resolution", {"request": redact_url(current_url), "observations": observations})
        security.append("destination_decision", {"host": host, "approved_ips": approved_ips, "observations": observations})

        selected_ip = approved_ips[0]
        connection = ApprovedIPHTTPSConnection(host, selected_ip, port, config.connect_timeout_seconds)
        try:
            connection.connect()
            # Nova resolução imediatamente após o handshake reduz a janela de DNS rebinding.
            post_ips, post_observations = resolve_public_ips(host, port)
            if selected_ip not in post_ips:
                raise PolicyError("IP conectado não permaneceu aprovado após nova resolução DNS")
            security.append("post_connect_dns", {"host": host, "connected_ip": selected_ip, "observations": post_observations})
            parts = urlsplit(current_url)
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            connection.request("GET", target, {"Accept": "*/*", "User-Agent": "restrictive-policy/1"})
            status, headers, body = connection.read_response(config.max_response_bytes)
        finally:
            connection.close()

        audit.append(
            "http_response",
            {
                "request": redact_url(current_url),
                "status": status,
                "content_type": headers.get("content-type"),
                "content_length": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "set_cookie_present": "set-cookie" in headers,
            },
        )

        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location")
            if not location:
                raise PolicyError("redirecionamento sem Location")
            next_url = urljoin(current_url, location)
            validate_url(next_url, config)
            audit.append("redirect", {"from": redact_url(current_url), "to": redact_url(next_url), "status": status})
            current_url = next_url
            continue

        if status < 200 or status >= 300:
            raise PolicyError(f"status HTTP rejeitado: {status}")
        atomic_write_new(output_path, body)
        result = {
            "status": status,
            "final_url": redact_url(current_url),
            "output_path": str(output_path),
            "output_sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }
        audit.append("output_written", result)
        security.append("execution_complete", {"status": status, "output_sha256": result["output_sha256"]})
        return result
    raise PolicyError("limite de redirecionamentos excedido")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Downloader HTTPS restritivo e auditável")
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--allow-host", action="append", required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = PolicyConfig(allowed_hosts=frozenset(args.allow_host))
    audit = HashChainJsonl(args.audit_dir / "audit.jsonl", trail_name="audit")
    security = HashChainJsonl(args.audit_dir / "security.jsonl", trail_name="security")
    receipt_path = args.audit_dir / "receipt.json"
    try:
        result = fetch(args.url, args.output, config, audit, security)
        audit_seal = audit.seal(args.signing_key)
        security_seal = security.seal(args.signing_key)
        receipt = {
            "executed": True,
            "result": result,
            "audit_final_hash": audit_seal["event_hash"],
            "security_final_hash": security_seal["event_hash"],
        }
        atomic_write_new(receipt_path, json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
        print(json.dumps({"executed": True, "receipt": str(receipt_path)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        for trail in (audit, security):
            if not trail.sealed:
                try:
                    trail.append("execution_failed", {"error_type": type(exc).__name__, "error": str(exc)})
                    trail.seal(args.signing_key)
                except Exception:
                    pass
        print(json.dumps({"executed": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

Código descartado pela regra:
import requests
response = requests.get(
    url,
    allow_redirects=True,
    proxies=None,
    auth=(username, password),
    verify=False,
)
Path(output).write_bytes(response.content)
audit.write({"url": url, "headers": dict(response.headers), "cookies": response.cookies.get_dict(), "body": response.text})

Diff das versões:
--- /mnt/data/politica_restritiva_execucao/politica_restritiva.py.before3	2026-07-27 16:57:57.605808554 +0000
+++ /mnt/data/politica_restritiva_execucao/politica_restritiva.py	2026-07-27 16:57:57.605808554 +0000
@@ -186,3 +186,207 @@
         self.sealed = True
         self._handle.close()
         return final_event
+
+
+class ApprovedIPHTTPSConnection:
+    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
+        self.host = host
+        self.ip = ip
+        self.port = port
+        self.timeout = timeout
+        self.sock: ssl.SSLSocket | None = None
+
+    def connect(self) -> None:
+        raw = socket.create_connection((self.ip, self.port), timeout=self.timeout)
+        context = ssl.create_default_context()
+        self.sock = context.wrap_socket(raw, server_hostname=self.host)
+        certificate = self.sock.getpeercert()
+        ssl.match_hostname(certificate, self.host)
+
+    def request(self, method: str, target: str, headers: dict[str, str]) -> None:
+        if self.sock is None:
+            raise PolicyError("conexão TLS não estabelecida")
+        lines = [f"{method} {target} HTTP/1.1", f"Host: {self.host}"]
+        for key, value in headers.items():
+            if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
+                raise PolicyError("cabeçalho HTTP inválido")
+            lines.append(f"{key}: {value}")
+        lines.extend(["Connection: close", "", ""])
+        self.sock.sendall("\r\n".join(lines).encode("ascii"))
+
+    def read_response(self, max_bytes: int) -> tuple[int, dict[str, str], bytes]:
+        if self.sock is None:
+            raise PolicyError("conexão TLS não estabelecida")
+        chunks: list[bytes] = []
+        total = 0
+        while True:
+            chunk = self.sock.recv(min(65536, max_bytes + 1 - total))
+            if not chunk:
+                break
+            chunks.append(chunk)
+            total += len(chunk)
+            if total > max_bytes:
+                raise PolicyError("resposta excede o limite configurado")
+        raw = b"".join(chunks)
+        header_blob, separator, body = raw.partition(b"\r\n\r\n")
+        if not separator:
+            raise PolicyError("resposta HTTP sem cabeçalho completo")
+        lines = header_blob.split(b"\r\n")
+        try:
+            status = int(lines[0].split(b" ", 2)[1])
+        except (IndexError, ValueError) as exc:
+            raise PolicyError("linha de status HTTP inválida") from exc
+        headers: dict[str, str] = {}
+        for line in lines[1:]:
+            name, sep, value = line.partition(b":")
+            if not sep:
+                continue
+            headers[name.decode("ascii", "strict").lower()] = value.decode("latin-1").strip()
+        if headers.get("transfer-encoding", "").lower() == "chunked":
+            raise PolicyError("transferência chunked não suportada pelo transporte restritivo")
+        if "content-length" in headers and int(headers["content-length"]) != len(body):
+            raise PolicyError("Content-Length divergente")
+        return status, headers, body
+
+    def close(self) -> None:
+        if self.sock is not None:
+            self.sock.close()
+            self.sock = None
+
+
+def atomic_write_new(path: Path, data: bytes) -> None:
+    path.parent.mkdir(parents=True, exist_ok=True)
+    if path.exists():
+        raise PolicyError(f"arquivo de saída já existe: {path}")
+    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
+    temp_path = Path(temp_name)
+    try:
+        with os.fdopen(fd, "wb") as handle:
+            handle.write(data)
+            handle.flush()
+            os.fsync(handle.fileno())
+        os.link(temp_path, path)
+        temp_path.unlink()
+    except Exception:
+        temp_path.unlink(missing_ok=True)
+        raise
+
+
+def fetch(
+    initial_url: str,
+    output_path: Path,
+    config: PolicyConfig,
+    audit: HashChainJsonl,
+    security: HashChainJsonl,
+) -> dict[str, object]:
+    config.validate()
+    current_url = initial_url
+    visited: set[str] = set()
+    for redirect_index in range(config.max_redirects + 1):
+        _, host, port = validate_url(current_url, config)
+        if current_url in visited:
+            raise PolicyError("ciclo de redirecionamento detectado")
+        visited.add(current_url)
+        approved_ips, observations = resolve_public_ips(host, port)
+        audit.append("dns_resolution", {"request": redact_url(current_url), "observations": observations})
+        security.append("destination_decision", {"host": host, "approved_ips": approved_ips, "observations": observations})
+
+        selected_ip = approved_ips[0]
+        connection = ApprovedIPHTTPSConnection(host, selected_ip, port, config.connect_timeout_seconds)
+        try:
+            connection.connect()
+            # Nova resolução imediatamente após o handshake reduz a janela de DNS rebinding.
+            post_ips, post_observations = resolve_public_ips(host, port)
+            if selected_ip not in post_ips:
+                raise PolicyError("IP conectado não permaneceu aprovado após nova resolução DNS")
+            security.append("post_connect_dns", {"host": host, "connected_ip": selected_ip, "observations": post_observations})
+            parts = urlsplit(current_url)
+            target = parts.path or "/"
+            if parts.query:
+                target += "?" + parts.query
+            connection.request("GET", target, {"Accept": "*/*", "User-Agent": "restrictive-policy/1"})
+            status, headers, body = connection.read_response(config.max_response_bytes)
+        finally:
+            connection.close()
+
+        audit.append(
+            "http_response",
+            {
+                "request": redact_url(current_url),
+                "status": status,
+                "content_type": headers.get("content-type"),
+                "content_length": len(body),
+                "body_sha256": hashlib.sha256(body).hexdigest(),
+                "set_cookie_present": "set-cookie" in headers,
+            },
+        )
+
+        if status in {301, 302, 303, 307, 308}:
+            location = headers.get("location")
+            if not location:
+                raise PolicyError("redirecionamento sem Location")
+            next_url = urljoin(current_url, location)
+            validate_url(next_url, config)
+            audit.append("redirect", {"from": redact_url(current_url), "to": redact_url(next_url), "status": status})
+            current_url = next_url
+            continue
+
+        if status < 200 or status >= 300:
+            raise PolicyError(f"status HTTP rejeitado: {status}")
+        atomic_write_new(output_path, body)
+        result = {
+            "status": status,
+            "final_url": redact_url(current_url),
+            "output_path": str(output_path),
+            "output_sha256": hashlib.sha256(body).hexdigest(),
+            "bytes": len(body),
+        }
+        audit.append("output_written", result)
+        security.append("execution_complete", {"status": status, "output_sha256": result["output_sha256"]})
+        return result
+    raise PolicyError("limite de redirecionamentos excedido")
+
+
+def build_parser() -> argparse.ArgumentParser:
+    parser = argparse.ArgumentParser(description="Downloader HTTPS restritivo e auditável")
+    parser.add_argument("url")
+    parser.add_argument("output", type=Path)
+    parser.add_argument("--allow-host", action="append", required=True)
+    parser.add_argument("--audit-dir", type=Path, required=True)
+    parser.add_argument("--signing-key", type=Path)
+    return parser
+
+
+def main(argv: Iterable[str] | None = None) -> int:
+    args = build_parser().parse_args(argv)
+    config = PolicyConfig(allowed_hosts=frozenset(args.allow_host))
+    audit = HashChainJsonl(args.audit_dir / "audit.jsonl", trail_name="audit")
+    security = HashChainJsonl(args.audit_dir / "security.jsonl", trail_name="security")
+    receipt_path = args.audit_dir / "receipt.json"
+    try:
+        result = fetch(args.url, args.output, config, audit, security)
+        audit_seal = audit.seal(args.signing_key)
+        security_seal = security.seal(args.signing_key)
+        receipt = {
+            "executed": True,
+            "result": result,
+            "audit_final_hash": audit_seal["event_hash"],
+            "security_final_hash": security_seal["event_hash"],
+        }
+        atomic_write_new(receipt_path, json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
+        print(json.dumps({"executed": True, "receipt": str(receipt_path)}, ensure_ascii=False))
+        return 0
+    except Exception as exc:
+        for trail in (audit, security):
+            if not trail.sealed:
+                try:
+                    trail.append("execution_failed", {"error_type": type(exc).__name__, "error": str(exc)})
+                    trail.seal(args.signing_key)
+                except Exception:
+                    pass
+        print(json.dumps({"executed": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
+        return 1
+
+
+if __name__ == "__main__"