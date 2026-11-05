"""BulkSMSBD (bulksmsbd.net) দিয়ে SMS পাঠানো। API key কখনো কোডে রাখা হয় না — env থেকে আসে।"""
import json
import logging
import re
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("hullor.sms")

# BulkSMSBD এর response code → (log এর জন্য মানে, কাস্টমারকে দেখানোর মেসেজ)
CODES = {
    1001: ("Invalid Number", "মোবাইল নম্বরটি সঠিক নয়।"),
    1002: ("Sender id not correct / disabled", None),
    1003: ("Required fields missing", None),
    1005: ("Internal Error", None),
    1006: ("Balance validity not available", None),
    1007: ("Balance insufficient", None),
    1011: ("User id not found", None),
    1012: ("Masking SMS must be sent in Bengali", None),
    1013: ("Sender id has no gateway for this api key", None),
    1014: ("Sender type name not found", None),
    1015: ("Sender id has no valid gateway", None),
    1018: ("Account owner is disabled", None),
    1031: ("Account not verified", None),
    1032: ("IP not whitelisted — BulkSMSBD ড্যাশবোর্ডে IP whitelist বন্ধ রাখুন (Render এর IP বদলায়)", None),
}
GENERIC = "এই মুহূর্তে SMS পাঠানো যাচ্ছে না। একটু পরে আবার চেষ্টা করুন।"


class SmsError(Exception):
    def __init__(self, user_message, code=None):
        super().__init__(user_message)
        self.user_message = user_message
        self.code = code


def to_intl(phone):
    """01XXXXXXXXX -> 8801XXXXXXXXX"""
    phone = re.sub(r"\D", "", phone or "")
    return phone if phone.startswith("88") else "88" + phone


def is_configured():
    return bool(settings.BULKSMSBD_API_KEY and settings.BULKSMSBD_SENDER_ID)


def send_sms(phone, message):
    if not is_configured():
        raise SmsError(GENERIC, code="not_configured")
    body = urllib.parse.urlencode({
        "api_key": settings.BULKSMSBD_API_KEY,
        "type": "text",
        "number": to_intl(phone),
        "senderid": settings.BULKSMSBD_SENDER_ID,
        "message": message,
    }).encode()
    req = urllib.request.Request(settings.BULKSMSBD_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # network / timeout / HTTP error
        logger.error("BulkSMSBD request failed: %s", exc)
        raise SmsError(GENERIC, code="network")
    try:
        code = int(json.loads(raw).get("response_code"))
    except Exception:
        m = re.search(r"\b(\d{3,4})\b", raw)
        code = int(m.group(1)) if m else 0
    if code == 202:
        return True
    meaning, user_msg = CODES.get(code, ("Unknown response", None))
    logger.error("BulkSMSBD rejected SMS: code=%s (%s) raw=%s", code, meaning, raw[:200])
    raise SmsError(user_msg or GENERIC, code=code)


def balance():
    """BulkSMSBD ব্যালেন্স (ডিবাগের জন্য)। ব্যর্থ হলে None।"""
    if not settings.BULKSMSBD_API_KEY:
        return None
    url = settings.BULKSMSBD_URL.rsplit("/", 1)[0] + "/getBalanceApi?" + urllib.parse.urlencode({"api_key": settings.BULKSMSBD_API_KEY})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:
        logger.error("BulkSMSBD balance failed: %s", exc)
        return None
