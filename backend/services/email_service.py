"""Transactional email via Resend (https://resend.com).

Only a single HTTPS endpoint is used, so there is no SDK dependency — we POST
JSON to the Resend API with the stdlib. All functions are blocking (network I/O)
and are meant to be called from async code via ``asyncio.to_thread``.

Configuration (set in Railway):
  RESEND_API_KEY   Resend API key (starts with ``re_``). Without it, emails are
                   NOT sent — the code is logged instead so the flow stays
                   testable during setup.
  EMAIL_FROM       From address, e.g. ``Zubchek <noreply@zubchek.com>``.
                   Defaults to Resend's shared testing sender, which can only
                   deliver to the Resend account owner's address.

These functions never raise: they return True on success, False otherwise, so a
mail hiccup can't 500 an auth request.
"""
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Zubchek <onboarding@resend.dev>"


def email_configured() -> bool:
    """True when a Resend API key is present (emails will actually be sent)."""
    return bool(os.getenv("RESEND_API_KEY"))


def _from_address() -> str:
    return os.getenv("EMAIL_FROM", _DEFAULT_FROM).strip() or _DEFAULT_FROM


def _post(payload: dict) -> bool:
    """POST a message payload to Resend. Returns True on 2xx."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.warning("RESEND_API_KEY not set — email to %s NOT sent", payload.get("to"))
        return False

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _RESEND_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.error("Resend returned status %s for %s", resp.status, payload.get("to"))
            return ok
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        logger.error("Resend HTTPError %s for %s: %s", e.code, payload.get("to"), detail)
        return False
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Resend send failed for %s: %s", payload.get("to"), e)
        return False


def send_code_email(to: str, code: str, purpose: str) -> bool:
    """Send a one-time code. ``purpose`` selects the wording.

    In dev (no API key) the code is logged so the flow can still be exercised.
    """
    if purpose == "doctor_verify":
        subject = "Zubchek — код подтверждения регистрации"
        intro = "Подтвердите вашу почту, чтобы завершить регистрацию врача."
    else:  # patient_login
        subject = "Zubchek — код для входа"
        intro = "Используйте этот код, чтобы войти в свой аккаунт Zubchek."

    if not email_configured():
        logger.warning("[DEV] Email code for %s (%s): %s", to, purpose, code)

    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1f2937">
      <h2 style="color:#7c3aed;margin:0 0 8px">Zubchek</h2>
      <p style="margin:0 0 16px;color:#4b5563">{intro}</p>
      <div style="font-size:34px;font-weight:800;letter-spacing:8px;color:#7c3aed;background:#f5f3ff;border:1px solid #ddd6fe;border-radius:12px;padding:16px;text-align:center">{code}</div>
      <p style="margin:16px 0 0;color:#9ca3af;font-size:13px">Код действителен 15 минут. Если вы не запрашивали этот код, просто проигнорируйте письмо.</p>
    </div>
    """
    return _post({
        "from": _from_address(),
        "to": [to],
        "subject": subject,
        "html": html,
    })


def send_report_email(to: str, patient_name: str, pdf_base64: str, filename: str) -> bool:
    """Email a report PDF (base64, no ``data:`` prefix) as an attachment."""
    if not email_configured():
        logger.warning("[DEV] Report email for %s (%s) NOT sent (no API key)", to, filename)
        return False

    name = (patient_name or "").strip()
    greeting = f"Здравствуйте, {name}!" if name else "Здравствуйте!"
    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1f2937">
      <h2 style="color:#7c3aed;margin:0 0 8px">Zubchek</h2>
      <p style="margin:0 0 12px;color:#4b5563">{greeting}</p>
      <p style="margin:0 0 12px;color:#4b5563">Ваш врач отправил вам отчёт о гигиене полости рта. Он прикреплён к этому письму в формате PDF.</p>
      <p style="margin:16px 0 0;color:#9ca3af;font-size:13px">zubchek.com • AI-анализ гигиены полости рта</p>
    </div>
    """
    return _post({
        "from": _from_address(),
        "to": [to],
        "subject": "Zubchek — ваш отчёт о гигиене полости рта",
        "html": html,
        "attachments": [{"filename": filename or "report.pdf", "content": pdf_base64}],
    })
