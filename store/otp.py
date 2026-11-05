import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import sms
from .models import PhoneOTP

logger = logging.getLogger("hullor.otp")

TTL_SECONDS = 5 * 60
RESEND_SECONDS = 60
MAX_PER_HOUR = 5
MAX_ATTEMPTS = 5
TOKEN_MAX_AGE = 30 * 60
SALT = "hullor.otp.checkout"


def _hash(phone, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _err(detail, code, **extra):
    return ValidationError({"detail": detail, "code": code, **extra})


def send_otp(phone, ip=None):
    now = timezone.now()
    last = PhoneOTP.objects.filter(phone=phone).first()
    if last:
        wait = RESEND_SECONDS - int((now - last.created_at).total_seconds())
        if wait > 0:
            raise _err(f"আবার কোড পেতে {wait} সেকেন্ড অপেক্ষা করুন।", "otp_wait", retry_after=wait)
    if PhoneOTP.objects.filter(phone=phone, created_at__gte=now - timedelta(hours=1)).count() >= MAX_PER_HOUR:
        raise _err("এই নম্বরে অনেকবার কোড পাঠানো হয়েছে। এক ঘণ্টা পর আবার চেষ্টা করুন।", "otp_limit")
    if PhoneOTP.objects.filter(created_at__gte=now - timedelta(hours=24)).count() >= settings.OTP_DAILY_LIMIT:
        logger.error("OTP daily limit reached")
        raise _err("আজকের জন্য কোড পাঠানোর সীমা শেষ। সরাসরি কল করে অর্ডার করুন।", "otp_limit")

    code = f"{secrets.randbelow(10 ** 6):06d}"
    row = PhoneOTP.objects.create(phone=phone, code_hash=_hash(phone, code), ip=ip,
                                  expires_at=now + timedelta(seconds=TTL_SECONDS))
    result = {"ok": True, "expires_in": TTL_SECONDS, "resend_in": RESEND_SECONDS}
    if not sms.is_configured():
        if settings.OTP_DEV_ECHO:  # শুধু লোকাল/টেস্টের জন্য: কোড রেসপন্সে ফেরত আসে
            logger.warning("SMS not configured — DEV OTP for %s is %s", phone, code)
            result["dev_code"] = code
            return result
        row.delete()
        logger.error("BULKSMSBD_API_KEY / BULKSMSBD_SENDER_ID সেট করা নেই")
        raise _err(sms.GENERIC, "sms_unavailable")
    try:
        sms.send_sms(phone, f"Your HULLOR verification code is {code}. Valid for 5 minutes. Do not share this code with anyone.")
    except sms.SmsError as exc:
        row.delete()
        raise _err(exc.user_message, "sms_failed")
    return result


def verify_otp(phone, code):
    """সঠিক হলে একবার-ব্যবহারযোগ্য signed token ফেরত দেয়।"""
    now = timezone.now()
    row = PhoneOTP.objects.filter(phone=phone, consumed=False, verified_at__isnull=True).first()
    if not row or row.expires_at < now:
        raise _err("কোডের মেয়াদ শেষ। নতুন কোড নিন।", "otp_expired")
    if row.attempts >= MAX_ATTEMPTS:
        raise _err("অনেকবার ভুল কোড দেওয়া হয়েছে। নতুন কোড নিন।", "otp_locked")
    row.attempts += 1
    row.save(update_fields=["attempts"])
    if not hmac.compare_digest(row.code_hash, _hash(phone, str(code).strip())):
        left = MAX_ATTEMPTS - row.attempts
        raise _err(f"কোডটি সঠিক নয়। আর {left} বার চেষ্টা করতে পারবেন।" if left > 0 else "অনেকবার ভুল কোড দেওয়া হয়েছে। নতুন কোড নিন।", "otp_invalid")
    row.verified_at = now
    row.save(update_fields=["verified_at"])
    return signing.dumps({"id": row.pk, "p": phone}, salt=SALT)


def check_token(token, phone):
    """অর্ডার করার সময় token যাচাই; যাচাই হলে row ফেরত দেয় (caller এটা consume করবে)।"""
    need = _err("অর্ডারের আগে মোবাইল নম্বর যাচাই করুন।", "otp_required")
    try:
        data = signing.loads(token or "", salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        raise need
    row = PhoneOTP.objects.select_for_update().filter(pk=data.get("id"), phone=phone, verified_at__isnull=False, consumed=False).first()
    if not row or data.get("p") != phone:
        raise need
    return row
