import json
import mimetypes
import os
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP(
    "email-server",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8001")),
    # Containers are reached through Docker service names, not localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _attach_file(message: EmailMessage, filename: str) -> bool:
    safe_name = os.path.basename(filename)
    path = ARTIFACTS_DIR / safe_name
    if not path.is_file():
        return False

    content_type, encoding = mimetypes.guess_type(safe_name)
    if content_type is None or encoding is not None:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)
    message.add_attachment(
        path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=safe_name,
    )
    return True


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
) -> str:
    """Send a real email over SMTP, or save a .eml file if SMTP is not configured."""
    _, address = parseaddr(to or "")
    if "@" not in address:
        return json.dumps(
            {"status": "error", "error": f"Invalid recipient: {to!r}"},
            ensure_ascii=False,
        )

    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "agent@localhost"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = subject or "Message from Mini AI Agent"
    message.set_content(body or "")

    attached: list[str] = []
    for filename in attachments or []:
        if _attach_file(message, filename):
            attached.append(os.path.basename(filename))

    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        file_path = ARTIFACTS_DIR / f"email-{uuid.uuid4().hex[:10]}.eml"
        file_path.write_bytes(message.as_bytes())
        payload = {
            "status": "saved",
            "transport": "file",
            "file": file_path.name,
            "size": file_path.stat().st_size,
            "to": address,
            "subject": message["Subject"],
            "attachments": attached,
        }
        print(f"[EMAIL SAVED] {payload}", flush=True)
        return json.dumps(payload, ensure_ascii=False)

    port = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = _env_bool("SMTP_SSL", port == 465)
    use_tls = _env_bool("SMTP_TLS", not use_ssl)

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(
                host,
                port,
                timeout=20,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if use_tls:
                server.starttls(context=ssl.create_default_context())

        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASSWORD", "")
        if user and password:
            server.login(user, password)

        server.send_message(message)
        server.quit()
    except Exception as exc:
        payload = {
            "status": "error",
            "transport": "smtp",
            "error": str(exc),
            "to": address,
        }
        print(f"[EMAIL ERROR] {payload}", flush=True)
        return json.dumps(payload, ensure_ascii=False)

    payload = {
        "status": "sent",
        "transport": "smtp",
        "to": address,
        "subject": message["Subject"],
        "attachments": attached,
    }
    print(f"[EMAIL SENT] {payload}", flush=True)
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
