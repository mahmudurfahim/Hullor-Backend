from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, Coupon, Order, Product, ProductVariant, SiteSetting

User = get_user_model()


@override_settings(OTP_DEV_ECHO=True)  # SMS কনফিগার ছাড়া টেস্টে OTP রেসপন্সে ফেরত আসে
class ShopFlowTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="শার্ট", slug="shirt")
        self.p = Product.objects.create(name="Test Shirt", code="tsh1", category=self.cat, price=500, old_price=800)
        self.v = ProductVariant.objects.create(product=self.p, size="M", color="Red", stock=5)
        self.v2 = ProductVariant.objects.create(product=self.p, size="L", color="Red", stock=1)
        Coupon.objects.create(code="SAVE10", discount_type="percent", value=10, min_order=500)

    def register(self, phone="01711111111"):
        r = self.client.post("/api/auth/register/", {"name": "Rakib", "phone": phone, "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        return r.data

    def checkout_payload(self, **kw):
        base = {"items": [{"variant_id": self.v.id, "quantity": 2}], "name": "Rakib", "phone": "+880 1711-111111",
                "district": "Dhaka", "address": "House 1, Road 2, Dhanmondi", "coupon_code": "save10"}
        base.update(kw)
        return base

    def test_auth_flow(self):
        self.register()
        self.assertEqual(self.client.get("/api/auth/me/").data["phone"], "01711111111")
        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"identifier": "০১৭১১১১১১১১", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 200)
        bad = self.client.post("/api/auth/login/", {"identifier": "01711111111", "password": "nope"}, format="json")
        self.assertEqual(bad.status_code, 400)
        dup = self.client.post("/api/auth/register/", {"name": "X", "phone": "01711111111", "password": "secret1"}, format="json")
        self.assertEqual(dup.status_code, 400)
        ref = self.client.post("/api/auth/refresh/", {"refresh": r.data["refresh"]}, format="json")
        self.assertEqual(ref.status_code, 200)

    def test_catalog(self):
        r = self.client.get("/api/products/?category=shirt&search=tsh")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["discount_percent"], 38)
        d = self.client.get("/api/products/tsh1/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(len(d.data["variants"]), 2)
        self.assertEqual(self.client.get("/api/categories/").data[0]["product_count"], 1)
        self.assertEqual(self.client.get("/api/products/?ordering=price_asc&in_stock=1").data["count"], 1)

    def test_cart_validate(self):
        r = self.client.post("/api/cart/validate/", {"items": [{"variant_id": self.v.id, "quantity": 2}], "coupon_code": "SAVE10"}, format="json")
        self.assertEqual(r.data["subtotal"], 1000)
        self.assertEqual(r.data["discount"], 100)
        self.assertEqual(r.data["total"], 900)
        over = self.client.post("/api/cart/validate/", {"items": [{"variant_id": self.v2.id, "quantity": 3}]}, format="json")
        self.assertFalse(over.data["ok"])

    # ------------------------------------------------------------ guest checkout + OTP
    def _verify_phone(self, phone="01711111111"):
        sent = self.client.post("/api/otp/send/", {"phone": phone}, format="json")
        self.assertEqual(sent.status_code, 200, sent.data)
        code = sent.data["dev_code"]  # SMS কনফিগার না থাকলে টেস্টে কোড ফেরত আসে
        ok = self.client.post("/api/otp/verify/", {"phone": phone, "code": code}, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        return ok.data["otp_token"]

    def test_guest_order_needs_otp(self):
        r = self.client.post("/api/orders/", self.checkout_payload(), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "otp_required")
        self.assertEqual(Order.objects.count(), 0)

    def test_guest_order_with_otp_and_track(self):
        token = self._verify_phone()
        r = self.client.post("/api/orders/", self.checkout_payload(otp_token=token), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(Order.objects.get().user)
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 3)
        # একই token দিয়ে দ্বিতীয় অর্ডার হবে না
        again = self.client.post("/api/orders/", self.checkout_payload(otp_token=token), format="json")
        self.assertEqual(again.status_code, 400)
        # গেস্ট নম্বর+ফোন দিয়ে ট্র্যাক করতে পারবে, ভুল ফোনে পারবে না
        num = r.data["number"]
        ok = self.client.get(f"/api/orders/track/?number={num}&phone=01711111111")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/track/?number={num}&phone=01799999999").status_code, 404)
        # গেস্ট অর্ডার লিস্ট দেখতে পারবে না
        self.assertEqual(self.client.get("/api/orders/").status_code, 401)

    def test_otp_token_bound_to_phone_and_wrong_code(self):
        token = self._verify_phone("01711111111")
        r = self.client.post("/api/orders/", self.checkout_payload(otp_token=token, phone="01822222222"), format="json")
        self.assertEqual(r.status_code, 400)
        self.client.post("/api/otp/send/", {"phone": "01833333333"}, format="json")
        bad = self.client.post("/api/otp/verify/", {"phone": "01833333333", "code": "000000"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.data["code"], "otp_invalid")

    def test_otp_resend_cooldown(self):
        self.client.post("/api/otp/send/", {"phone": "01711111111"}, format="json")
        r = self.client.post("/api/otp/send/", {"phone": "01711111111"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "otp_wait")

    def test_otp_off_allows_plain_guest_order(self):
        s = SiteSetting.load(); s.require_otp = False; s.save()
        r = self.client.post("/api/orders/", self.checkout_payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_otp_sms_gateway(self):
        from unittest import mock

        from django.test import override_settings

        with override_settings(BULKSMSBD_API_KEY="k", BULKSMSBD_SENDER_ID="880961", OTP_DEV_ECHO=False):
            captured = {}

            class Resp:
                def __init__(self, body): self.body = body
                def read(self): return self.body
                def __enter__(self): return self
                def __exit__(self, *a): return False

            def fake_ok(req, timeout=0):
                captured["body"] = req.data.decode()
                return Resp(b'{"response_code":202,"success_message":"SMS Submitted Successfully"}')

            with mock.patch("store.sms.urllib.request.urlopen", fake_ok):
                r = self.client.post("/api/otp/send/", {"phone": "01711111111"}, format="json")
            self.assertEqual(r.status_code, 200, r.data)
            self.assertNotIn("dev_code", r.data)
            self.assertIn("number=8801711111111", captured["body"])
            self.assertIn("senderid=880961", captured["body"])
            # গেটওয়ে ব্যর্থ (যেমন ব্যালেন্স শেষ 1007) হলে ক্লিন এরর, OTP row থাকে না
            Order.objects.all().delete()
            from .models import PhoneOTP
            PhoneOTP.objects.all().delete()
            with mock.patch("store.sms.urllib.request.urlopen", lambda req, timeout=0: Resp(b'{"response_code":1007}')):
                r = self.client.post("/api/otp/send/", {"phone": "01711111111"}, format="json")
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.data["code"], "sms_failed")
            self.assertEqual(PhoneOTP.objects.count(), 0)

    def test_sms_not_configured_in_production(self):
        from django.test import override_settings

        with override_settings(OTP_DEV_ECHO=False):
            r = self.client.post("/api/otp/send/", {"phone": "01711111111"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "sms_unavailable")

    # ------------------------------------------------------------ bilingual customer data + content
    def test_order_language_fields(self):
        s = SiteSetting.load(); s.require_otp = False; s.save()
        self.client.post("/api/orders/", self.checkout_payload(name="Rakib Hasan", address="House 1, Road 2, Dhanmondi", note="Call me", coupon_code=""), format="json")
        self.client.post("/api/orders/", self.checkout_payload(name="রাকিব", address="বাসা ১, রোড ২, ধানমন্ডি", note="", coupon_code=""), format="json")
        en_o, bn_o = Order.objects.order_by("id")
        self.assertEqual((en_o.customer_name_en, en_o.customer_name_bn, en_o.address_en, en_o.address_bn, en_o.note_en, en_o.note_bn),
                         ("Rakib Hasan", "", "House 1, Road 2, Dhanmondi", "", "Call me", ""))
        self.assertEqual((bn_o.customer_name_bn, bn_o.customer_name_en, bn_o.address_bn, bn_o.address_en, bn_o.note_bn, bn_o.note_en),
                         ("রাকিব", "", "বাসা ১, রোড ২, ধানমন্ডি", "", "", ""))
        self.assertEqual(bn_o.customer_name, "রাকিব")

    def test_public_lang_param(self):
        s = SiteSetting.load()
        self.assertEqual(self.client.get("/api/settings/").data["announcement"], "সারা বাংলাদেশে ক্যাশ অন ডেলিভারি")
        self.assertEqual(self.client.get("/api/settings/?lang=en").data["announcement"], "Cash on delivery across Bangladesh")
        s.announcement_en = ""; s.save()
        self.assertEqual(self.client.get("/api/settings/?lang=en").data["announcement"], "সারা বাংলাদেশে ক্যাশ অন ডেলিভারি")
        self.p.name, self.p.name_en = "টেস্ট শার্ট", "Test Shirt EN"; self.p.save()
        self.cat.name_en = "Shirts"; self.cat.save()
        bn = self.client.get(f"/api/products/{self.p.slug}/").data
        en = self.client.get(f"/api/products/{self.p.slug}/?lang=en").data
        self.assertEqual((bn["name"], bn["category"]["name"]), ("টেস্ট শার্ট", "শার্ট"))
        self.assertEqual((en["name"], en["category"]["name"]), ("Test Shirt EN", "Shirts"))

    def test_order_cod_stock_and_cancel(self):
        self.register()
        r = self.client.post("/api/orders/", self.checkout_payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["total"], 900)
        self.assertEqual(r.data["payment_method"], "cod")
        self.assertEqual(r.data["phone"], "01711111111")
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 3)
        self.assertEqual(Coupon.objects.get(code="SAVE10").used_count, 1)
        num = r.data["number"]
        self.assertEqual(len(self.client.get("/api/orders/").data["results"]), 1)
        self.assertEqual(self.client.get(f"/api/orders/{num}/").data["items"][0]["quantity"], 2)
        c = self.client.post(f"/api/orders/{num}/cancel/")
        self.assertEqual(c.data["status"], "cancelled")
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 5)

    def test_oversell_blocked(self):
        self.register()
        r = self.client.post("/api/orders/", self.checkout_payload(items=[{"variant_id": self.v2.id, "quantity": 2}], coupon_code=""), format="json")
        self.assertEqual(r.status_code, 400)
        self.v2.refresh_from_db()
        self.assertEqual(self.v2.stock, 1)

    def test_other_user_cannot_see_order(self):
        self.register()
        num = self.client.post("/api/orders/", self.checkout_payload(), format="json").data["number"]
        self.register("01822222222")
        self.assertEqual(self.client.get(f"/api/orders/{num}/").status_code, 404)

    def test_delivery_charge(self):
        s = SiteSetting.load()
        s.delivery_charge_dhaka, s.delivery_charge_outside = 60, 120
        s.save()
        d = self.client.post("/api/cart/validate/", {"items": [{"variant_id": self.v.id, "quantity": 1}], "district": "Dhaka"}, format="json").data
        o = self.client.post("/api/cart/validate/", {"items": [{"variant_id": self.v.id, "quantity": 1}], "district": "Sylhet"}, format="json").data
        self.assertEqual((d["delivery_charge"], o["delivery_charge"]), (60, 120))

    def test_wishlist_and_review(self):
        self.register()
        self.assertTrue(self.client.post("/api/wishlist/", {"product_id": self.p.id}, format="json").data["wishlisted"])
        self.assertEqual(self.client.get("/api/wishlist/").data["ids"], [self.p.id])
        self.assertEqual(self.client.post("/api/products/tsh1/reviews/", {"rating": 5}, format="json").status_code, 403)
        num = self.client.post("/api/orders/", self.checkout_payload(coupon_code=""), format="json").data["number"]
        order = Order.objects.get(number=num)
        from .services import set_order_status
        set_order_status(order, "delivered")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "paid")
        r = self.client.post("/api/products/tsh1/reviews/", {"rating": 4, "comment": "ভালো"}, format="json")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(self.client.get("/api/products/").data["results"][0]["rating_avg"], 4.0)


class AdminApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("01700000000", "pw12345", name="Admin")
        self.user = User.objects.create_user("01711111111", "pw12345", name="User")

    def login(self, user):
        r = self.client.post("/api/auth/login/", {"identifier": user.phone, "password": "pw12345"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])

    def test_customer_forbidden(self):
        self.login(self.user)
        self.assertEqual(self.client.get("/api/admin/dashboard/").status_code, 403)
        self.client.credentials()
        self.assertEqual(self.client.get("/api/admin/dashboard/").status_code, 401)

    def test_admin_settings_bilingual_and_about_image(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        self.login(self.admin)
        buf = io.BytesIO(); Image.new("RGB", (30, 30), "blue").save(buf, "PNG")
        r = self.client.patch("/api/admin/settings/", {
            "announcement": "সারা বাংলাদেশে ক্যাশ অন ডেলিভারি", "announcement_en": "Cash on delivery nationwide",
            "about_title_en": "Our story", "about_text_en": "Para one\n\nPara two", "require_otp": "false",
            "free_delivery_above": "", "delivery_charge_dhaka": "60",
            "about_image": SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png"),
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["about_image_src"])
        self.assertIsNone(r.data["free_delivery_above"])
        self.assertFalse(r.data["require_otp"])
        self.client.credentials()
        pub = self.client.get("/api/settings/?lang=en").data
        self.assertEqual(pub["announcement"], "Cash on delivery nationwide")
        self.assertEqual(pub["about_title"], "Our story")
        self.assertTrue(pub["about_image"])
        self.assertNotIn("require_otp", pub)
        self.login(self.admin)
        b = self.client.post("/api/admin/banners/", {"title": "বড় অফার", "title_en": "Big offer", "button_text_en": "Shop now"}, format="json")
        self.assertEqual(b.status_code, 201, b.data)
        self.client.credentials()
        self.assertEqual(self.client.get("/api/banners/?lang=en").data[0]["title"], "Big offer")
        self.assertEqual(self.client.get("/api/banners/").data[0]["title"], "বড় অফার")

    def test_admin_catalog_crud_and_orders(self):
        self.login(self.admin)
        c = self.client.post("/api/admin/categories/", {"name": "Polo"}, format="json")
        self.assertEqual(c.status_code, 201, c.data)
        p = self.client.post("/api/admin/products/", {
            "name": "Polo Shirt", "category": c.data["id"], "price": 400, "old_price": 600,
            "variants": [{"size": "M", "color": "Green", "stock": 10}, {"size": "L", "color": "Green", "stock": 0}],
        }, format="json")
        self.assertEqual(p.status_code, 201, p.data)
        self.assertTrue(p.data["code"].startswith("HL"))
        self.assertEqual(p.data["total_stock"], 10)
        pid, vid = p.data["id"], p.data["variants"][0]["id"]
        u = self.client.patch(f"/api/admin/products/{pid}/", {"variants": [{"id": vid, "size": "M", "color": "Green", "stock": 7}]}, format="json")
        self.assertEqual(u.status_code, 200, u.data)
        self.assertEqual(len(u.data["variants"]), 1)
        img = self.client.post(f"/api/admin/products/{pid}/images/", {"url": "https://example.com/a.jpg"}, format="json")
        self.assertEqual(img.status_code, 201, img.data)
        self.assertEqual(self.client.delete(f"/api/admin/products/{pid}/images/{img.data[0]['id']}/").status_code, 204)

        # customer places order
        self.login(self.user)
        o = self.client.post("/api/orders/", {"items": [{"variant_id": vid, "quantity": 2}], "name": "U", "phone": "01711111111",
                                              "district": "Dhaka", "address": "Somewhere long address"}, format="json")
        self.assertEqual(o.status_code, 201, o.data)
        self.login(self.admin)
        lst = self.client.get("/api/admin/orders/?status=pending")
        self.assertEqual(lst.data["count"], 1)
        st = self.client.post(f"/api/admin/orders/{o.data['id']}/status/", {"status": "shipped", "note": "Pathao"}, format="json")
        self.assertEqual(st.data["status"], "shipped")
        self.assertEqual(len(st.data["history"]), 2)
        self.client.post(f"/api/admin/orders/{o.data['id']}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(self.client.get(f"/api/admin/products/{pid}/").data["total_stock"], 7)
        d = self.client.get("/api/admin/dashboard/")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(len(d.data["sales_by_day"]), 14)
        self.assertEqual(self.client.get("/api/admin/customers/").data["count"], 2)
        self.assertEqual(self.client.get("/api/admin/orders/counts/").data["cancelled"], 1)
        self.assertEqual(self.client.patch("/api/admin/settings/", {"delivery_charge_outside": 120}, format="json").data["delivery_charge_outside"], 120)
        cp = self.client.post("/api/admin/coupons/", {"code": "x1", "discount_type": "fixed", "value": 50}, format="json")
        self.assertEqual(cp.data["code"], "X1")
