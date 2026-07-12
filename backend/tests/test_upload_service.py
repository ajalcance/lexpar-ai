"""
File: tests/test_upload_service.py
Purpose: The PDF active-content gate (upload_service.scan_pdf_active_content) — the
    PDF-appropriate malware guard: every dangerous name token fires with a readable reason,
    PDF-name boundaries prevent false positives (/AAPL, /JSX), clean documents pass, and the
    route surfaces a 422 with remediation guidance.
Depends on: pytest, app/services/upload_service.py
"""

from app.services.upload_service import scan_pdf_active_content

AGENT = {"X-Agent-Token": "test-agent-token"}


def _pdf(body: bytes) -> bytes:
    return b"%PDF-1.7\n" + body + b"\n%%EOF"


def test_every_threat_token_fires():
    cases = {
        b"<< /Type /Action /S /JavaScript (app.alert(1)) >>": "embedded JavaScript",
        b"<< /JS (this.exportDataObject) >>": "embedded JavaScript",
        b"<< /OpenAction 5 0 R >>": "an auto-run open action",
        b"<< /AA << /O 6 0 R >> >>": "auto-run actions",
        b"<< /S /Launch /F (cmd.exe) >>": "a launch action",
        b"<< /Type /EmbeddedFile /Length 99 >>": "an embedded file attachment",
        b"<< /Subtype /RichMedia >>": "embedded rich media",
        b"<< /XFA 7 0 R >>": "XFA form scripting",
        b"trailer << /Encrypt 8 0 R >>": "encryption (the file cannot be inspected or ingested)",
    }
    for body, reason in cases.items():
        assert scan_pdf_active_content(_pdf(body)) == reason, body


def test_pdf_name_boundaries_prevent_false_positives():
    # /AAPL (macOS metadata) must not trip /AA; /JSX must not trip /JS; token at end-of-data fires.
    assert scan_pdf_active_content(_pdf(b"<< /AAPL:Keywords (brief) >>")) is None
    assert scan_pdf_active_content(_pdf(b"<< /JSXTransform (x) >>")) is None
    assert scan_pdf_active_content(b"%PDF-1.7 /JS") == "embedded JavaScript"


def test_clean_pdf_passes():
    clean = _pdf(
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Contents 4 0 R >> endobj"
    )
    assert scan_pdf_active_content(clean) is None


def test_upload_route_rejects_active_content_with_remediation(client, auth_headers):
    case = client.post(
        "/api/cases", headers=auth_headers, json={"title": "T", "case_facts": "F"}
    ).json()
    resp = client.post(
        f"/api/cases/{case['id']}/documents",
        headers=auth_headers,
        files={
            "file": (
                "malicious.pdf",
                _pdf(b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>"),
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 422
    assert "flattened" in resp.json()["detail"]
