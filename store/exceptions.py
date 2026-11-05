import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("hullor.api")


def _storage_error_message(exc):
    """ছবি আপলোড (Supabase/S3) এর সাধারণ সমস্যাগুলো বুঝিয়ে বলে। secret কখনো দেখায় না।"""
    name = type(exc).__name__
    text = str(exc)
    code = ""
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = (resp.get("Error") or {}).get("Code", "")
    hints = {
        "NoSuchBucket": "Bucket পাওয়া যায়নি। SUPABASE_S3_BUCKET এর নাম ঠিক আছে কিনা এবং Supabase এ bucket তৈরি করা আছে কিনা দেখুন।",
        "InvalidAccessKeyId": "SUPABASE_S3_ACCESS_KEY ভুল।",
        "SignatureDoesNotMatch": "SUPABASE_S3_SECRET_KEY ভুল, অথবা SUPABASE_S3_REGION মেলেনি।",
        "AccessDenied": "Storage এ লেখার অনুমতি নেই। Supabase এ S3 access key ও bucket policy দেখুন।",
        "InvalidBucketName": "Bucket এর নামে ভুল আছে।",
    }
    if code in hints:
        return f"ছবি সেভ হয়নি ({code}): {hints[code]}"
    if "Could not connect to the endpoint" in text or "EndpointConnectionError" in name:
        return "ছবি সেভ হয়নি: SUPABASE_S3_ENDPOINT এ পৌঁছানো যাচ্ছে না। URL টি .../storage/v1/s3 দিয়ে শেষ হয়েছে কিনা দেখুন।"
    if "Invalid endpoint" in text or "ValueError" in name:
        return "ছবি সেভ হয়নি: SUPABASE_S3_ENDPOINT সঠিক নয় (https:// দিয়ে শুরু হতে হবে)।"
    return f"ছবি সেভ হয়নি ({name}{': ' + code if code else ''})। Render Logs দেখুন।"


def api_exception_handler(exc, context):
    """সব error কে একটা সহজ shape এ আনে: {detail, errors}. ফ্রন্টএন্ড এখান থেকে মেসেজ দেখায়।"""
    response = exception_handler(exc, context)
    if response is None:
        # DRF যেটা সামলায়নি (অর্থাৎ ৫০০)। storage সমস্যা হলে পরিষ্কার মেসেজ দিই, সব ক্ষেত্রেই Logs এ traceback রাখি।
        mod = type(exc).__module__ or ""
        if mod.startswith(("botocore", "boto3", "storages", "s3transfer")):
            logger.exception("Storage error on %s", getattr(context.get("request"), "path", "?"), exc_info=exc)
            msg = _storage_error_message(exc)
            return Response({"detail": msg}, status=502)
        logger.exception("Unhandled error on %s", getattr(context.get("request"), "path", "?"), exc_info=exc)
        return None
    data = response.data
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is None:
            first = next(iter(data.values()), None)
            while isinstance(first, (list, tuple)) and first:
                first = first[0]
            if isinstance(first, dict):
                first = next(iter(first.values()), "")
                while isinstance(first, (list, tuple)) and first:
                    first = first[0]
            detail = str(first) if first else "অনুরোধটি সম্পন্ন করা যায়নি।"
            response.data = {"detail": detail, "errors": data}
        else:
            response.data = {**data, "detail": str(detail)}
    elif isinstance(data, list):
        response.data = {"detail": str(data[0]) if data else "Error", "errors": data}
    return response
