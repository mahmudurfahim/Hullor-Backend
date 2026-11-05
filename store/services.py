from collections import OrderedDict

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .lang import split_bn_en
from .models import Coupon, Order, OrderItem, OrderStatusHistory, ProductVariant, SiteSetting
from .utils import product_image_urls

MAX_QTY_PER_LINE = 20


def delivery_charge_for(subtotal, district, setting=None):
    setting = setting or SiteSetting.load()
    if subtotal <= 0:
        return 0
    if setting.free_delivery_above and subtotal >= setting.free_delivery_above:
        return 0
    inside_dhaka = (district or "dhaka").strip().lower() in ("dhaka", "ঢাকা")
    return setting.delivery_charge_dhaka if inside_dhaka else setting.delivery_charge_outside


def price_cart(items, coupon_code="", district="", request=None, lock=False):
    """কার্টের আইটেমগুলো ডাটাবেজের আসল দাম/স্টক দিয়ে যাচাই করে মোট হিসাব বের করে।
    items = [{"variant_id": 1, "quantity": 2}, ...]"""
    merged = OrderedDict()
    for it in items:
        vid = int(it["variant_id"])
        merged[vid] = merged.get(vid, 0) + int(it["quantity"])

    qs = ProductVariant.objects.select_related("product").prefetch_related("product__images").filter(pk__in=merged.keys())
    if lock:
        qs = qs.select_for_update(of=("self",))
    variants = {v.pk: v for v in qs}

    lines, subtotal, ok = [], 0, True
    for vid, qty in merged.items():
        variant = variants.get(vid)
        if variant is None or not variant.product.is_active:
            ok = False
            lines.append({"variant_id": vid, "available": False, "ok": False, "quantity": qty, "stock": 0,
                          "name": "অনুপলব্ধ পণ্য", "error": "এই পণ্যটি আর পাওয়া যাচ্ছে না।"})
            continue
        product = variant.product
        qty = min(qty, MAX_QTY_PER_LINE)
        line_ok = variant.stock >= qty and variant.stock > 0
        error = None
        if not line_ok:
            ok = False
            error = "স্টক শেষ।" if variant.stock == 0 else f"মাত্র {variant.stock}টি স্টকে আছে।"
        eff_qty = qty if line_ok else min(qty, variant.stock)
        images = product_image_urls(product, request)
        lines.append({
            "variant_id": variant.pk, "product_id": product.pk, "slug": product.slug, "code": product.code,
            "name": product.name, "size": variant.size, "color": variant.color, "color_hex": variant.color_hex,
            "price": product.price, "old_price": product.old_price, "image": images[0] if images else None,
            "quantity": eff_qty, "requested_quantity": qty, "stock": variant.stock,
            "available": True, "ok": line_ok, "error": error, "line_total": product.price * eff_qty,
        })
        subtotal += product.price * eff_qty

    discount, coupon, coupon_error = 0, None, None
    code = (coupon_code or "").strip().upper()
    if code:
        cq = Coupon.objects.select_for_update() if lock else Coupon.objects
        coupon = cq.filter(code=code).first()
        if not coupon:
            coupon_error = "কুপন কোডটি সঠিক নয়।"
        else:
            discount, coupon_error = coupon.evaluate(subtotal)
            if coupon_error:
                discount = 0
    delivery = delivery_charge_for(subtotal - discount, district)
    return {
        "lines": lines, "subtotal": subtotal, "discount": discount, "delivery_charge": delivery,
        "total": max(subtotal - discount, 0) + delivery, "ok": ok and bool(lines),
        "coupon": {"code": coupon.code, "discount": discount} if coupon and not coupon_error else None,
        "coupon_error": coupon_error, "_coupon_obj": coupon if coupon and not coupon_error else None,
    }


@transaction.atomic
def create_order(user, data, request=None):
    priced = price_cart(data["items"], data.get("coupon_code", ""), data["district"], request, lock=True)
    if not priced["lines"]:
        raise ValidationError({"detail": "আপনার কার্ট খালি।"})
    bad = [l for l in priced["lines"] if not l["ok"]]
    if bad:
        raise ValidationError({"detail": f"{bad[0]['name']}: {bad[0]['error']} কার্ট আপডেট করে আবার চেষ্টা করুন.", "code": "cart_changed"})
    if data.get("coupon_code") and priced["coupon_error"]:
        raise ValidationError({"detail": priced["coupon_error"], "code": "coupon"})

    name_bn, name_en = split_bn_en(data["name"])
    addr_bn, addr_en = split_bn_en(data["address"])
    note_bn, note_en = split_bn_en(data.get("note", ""))
    order = Order.objects.create(
        user=user, customer_name_bn=name_bn, customer_name_en=name_en, address_bn=addr_bn, address_en=addr_en,
        note_bn=note_bn, note_en=note_en, customer_name=data["name"], phone=data["phone"], email=data.get("email", "") or "",
        district=data["district"], address=data["address"], note=data.get("note", ""),
        subtotal=priced["subtotal"], discount=priced["discount"], delivery_charge=priced["delivery_charge"],
        total=priced["total"], coupon_code=priced["coupon"]["code"] if priced["coupon"] else "",
    )
    for line in priced["lines"]:
        OrderItem.objects.create(
            order=order, product_id=line["product_id"], variant_id=line["variant_id"], name=line["name"],
            code=line["code"], size=line["size"], color=line["color"], price=line["price"],
            quantity=line["quantity"], image=line["image"] or "",
        )
        ProductVariant.objects.filter(pk=line["variant_id"]).update(stock=_stock_minus(line))
    coupon = priced["_coupon_obj"]
    if coupon:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])
    OrderStatusHistory.objects.create(order=order, status=Order.PENDING, note="অর্ডার করা হয়েছে")
    return order


def _stock_minus(line):
    from django.db.models import F

    return F("stock") - line["quantity"]


@transaction.atomic
def set_order_status(order, new_status, note=""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if new_status == order.status:
        return order
    valid = {s for s, _ in Order.STATUS_CHOICES}
    if new_status not in valid:
        raise ValidationError({"detail": "অবৈধ স্ট্যাটাস।"})

    from django.db.models import F

    closing = new_status in (Order.CANCELLED, Order.RETURNED)
    if closing and not order.stock_restored:
        for item in order.items.all():
            if item.variant_id:
                ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") + item.quantity)
        order.stock_restored = True
    elif not closing and order.stock_restored:
        # বাতিল অর্ডার আবার চালু করা হচ্ছে — স্টক আবার কাটতে হবে
        items = list(order.items.select_related("variant"))
        for item in items:
            if item.variant_id and item.variant.stock < item.quantity:
                raise ValidationError({"detail": f"{item.name} ({item.size}) এর পর্যাপ্ত স্টক নেই।"})
        for item in items:
            if item.variant_id:
                ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") - item.quantity)
        order.stock_restored = False

    order.status = new_status
    order.payment_status = "paid" if new_status == Order.DELIVERED else "unpaid"
    order.save()
    OrderStatusHistory.objects.create(order=order, status=new_status, note=note[:255])
    return order
