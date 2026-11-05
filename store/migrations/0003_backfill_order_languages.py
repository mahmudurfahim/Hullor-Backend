import re

from django.db import migrations

BN = re.compile(r"[\u0980-\u09FF]")


def backfill(apps, schema_editor):
    """পুরনো অর্ডারের নাম/ঠিকানা/নোট ভাষা অনুযায়ী _bn / _en ফিল্ডে ভাগ করে দেয়।"""
    Order = apps.get_model("store", "Order")
    for o in Order.objects.all().iterator():
        for src, bn_f, en_f in (("customer_name", "customer_name_bn", "customer_name_en"),
                                ("address", "address_bn", "address_en"),
                                ("note", "note_bn", "note_en")):
            text = (getattr(o, src) or "").strip()
            if not text:
                continue
            setattr(o, bn_f if BN.search(text) else en_f, text)
        o.save(update_fields=["customer_name_bn", "customer_name_en", "address_bn", "address_en", "note_bn", "note_en"])


class Migration(migrations.Migration):
    dependencies = [("store", "0002_otp_bilingual_about")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
