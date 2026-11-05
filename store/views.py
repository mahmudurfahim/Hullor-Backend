from django.db import transaction
from django.db.models import Avg, Count, Q
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from accounts.serializers import clean_phone
from . import otp as otp_service
from .models import Banner, Category, Order, OrderItem, Product, Review, SiteSetting, WishlistItem
from .serializers import (
    BannerSerializer, CartInput, CategorySerializer, CheckoutInput, OrderDetailSerializer, OrderListSerializer,
    ProductDetailSerializer, ProductListSerializer, ReviewSerializer, SiteSettingSerializer,
)
from .services import create_order, price_cart, set_order_status

ORDERINGS = {
    "newest": ["-created_at", "-id"],
    "price_asc": ["price", "id"],
    "price_desc": ["-price", "-id"],
    "rating": ["-rating_avg", "-id"],
    "name": ["name"],
}


def public_products():
    return (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("images", "variants")
        .annotate(
            rating_avg=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
            rating_count=Count("reviews", filter=Q(reviews__is_approved=True), distinct=True),
        )
    )


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class SettingsView(APIView):
    def get(self, request):
        return Response(SiteSettingSerializer(SiteSetting.load(), context={"request": request}).data)


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")) or None


class OtpSendView(APIView):
    """POST {phone} — মোবাইলে ৬ ডিজিটের কোড SMS করে।"""

    throttle_scope = "otp"

    def post(self, request):
        try:
            phone = clean_phone(request.data.get("phone", ""))
        except Exception as exc:
            raise ValidationError({"detail": getattr(exc, "detail", None) and str(exc.detail[0]) or "সঠিক মোবাইল নম্বর দিন (যেমন: 01XXXXXXXXX)।"})
        return Response(otp_service.send_otp(phone, _client_ip(request)))


class OtpVerifyView(APIView):
    """POST {phone, code} — ঠিক হলে অর্ডারের জন্য otp_token ফেরত দেয়।"""

    throttle_scope = "otp"

    def post(self, request):
        try:
            phone = clean_phone(request.data.get("phone", ""))
        except Exception:
            raise ValidationError({"detail": "সঠিক মোবাইল নম্বর দিন (যেমন: 01XXXXXXXXX)।"})
        code = str(request.data.get("code", "")).strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError({"detail": "৬ ডিজিটের কোড দিন।", "code": "otp_invalid"})
        return Response({"verified": True, "otp_token": otp_service.verify_otp(phone, code)})


class BannerListView(APIView):
    def get(self, request):
        qs = Banner.objects.filter(is_active=True)
        return Response(BannerSerializer(qs, many=True, context={"request": request}).data)


class CategoryListView(APIView):
    def get(self, request):
        qs = Category.objects.filter(is_active=True).annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        )
        return Response(CategorySerializer(qs, many=True, context={"request": request}).data)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductListSerializer

    def get_queryset(self):
        qs = public_products()
        p = self.request.query_params
        if self.action != "list":
            return qs
        if p.get("category"):
            qs = qs.filter(category__slug=p["category"])
        if p.get("search"):
            for term in p["search"].split()[:5]:
                qs = qs.filter(
                    Q(name__icontains=term) | Q(code__icontains=term) | Q(description__icontains=term)
                    | Q(category__name__icontains=term)
                )
        if p.get("featured") in ("1", "true"):
            qs = qs.filter(is_featured=True)
        if p.get("on_sale") in ("1", "true"):
            qs = qs.filter(old_price__isnull=False)
        if p.get("min_price", "").isdigit():
            qs = qs.filter(price__gte=int(p["min_price"]))
        if p.get("max_price", "").isdigit():
            qs = qs.filter(price__lte=int(p["max_price"]))
        if p.get("in_stock") in ("1", "true"):
            qs = qs.filter(variants__stock__gt=0).distinct()
        if p.get("size"):
            qs = qs.filter(variants__size__iexact=p["size"], variants__stock__gt=0).distinct()
        return qs.order_by(*ORDERINGS.get(p.get("ordering"), ORDERINGS["newest"]))

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        data = ProductDetailSerializer(product, context={"request": request}).data
        related = public_products().exclude(pk=product.pk)
        if product.category_id:
            related = related.filter(category_id=product.category_id)
        data["related"] = ProductListSerializer(related[:4], many=True, context={"request": request}).data
        return Response(data)

    @action(detail=True, methods=["get", "post"], url_path="reviews", permission_classes=[permissions.AllowAny])
    def reviews(self, request, slug=None):
        product = self.get_object()
        user = request.user if request.user.is_authenticated else None
        purchased = bool(user) and OrderItem.objects.filter(
            product=product, order__user=user, order__status=Order.DELIVERED
        ).exists()

        if request.method == "POST":
            if not user:
                return Response({"detail": "রিভিউ দিতে লগইন করুন।"}, status=401)
            if not purchased:
                return Response({"detail": "পণ্যটি ডেলিভারি পাওয়ার পর রিভিউ দিতে পারবেন।"}, status=403)
            try:
                rating = int(request.data.get("rating"))
            except (TypeError, ValueError):
                rating = 0
            if not 1 <= rating <= 5:
                return Response({"detail": "১ থেকে ৫ এর মধ্যে রেটিং দিন।"}, status=400)
            Review.objects.update_or_create(
                user=user, product=product,
                defaults={"rating": rating, "comment": str(request.data.get("comment", ""))[:1000], "is_approved": True},
            )

        qs = product.reviews.filter(is_approved=True).select_related("user")
        agg = qs.aggregate(avg=Avg("rating"), count=Count("id"))
        return Response({
            "results": ReviewSerializer(qs[:50], many=True).data,
            "avg": round(agg["avg"], 1) if agg["avg"] else 0,
            "count": agg["count"],
            "can_review": purchased,
            "has_reviewed": bool(user) and product.reviews.filter(user=user).exists(),
        })


class WishlistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True)
        ids = list(items)
        products = public_products().filter(pk__in=ids)
        order = {pid: i for i, pid in enumerate(ids)}
        products = sorted(products, key=lambda p: order[p.pk])
        return Response({
            "ids": ids,
            "products": ProductListSerializer(products, many=True, context={"request": request}).data,
        })

    def post(self, request):
        """toggle"""
        product = Product.objects.filter(pk=request.data.get("product_id"), is_active=True).first()
        if not product:
            return Response({"detail": "পণ্যটি পাওয়া যায়নি।"}, status=404)
        obj, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            obj.delete()
        return Response({"wishlisted": created, "product_id": product.pk})


class CartValidateView(APIView):
    """কার্টের আইটেম + কুপন + জেলা পাঠালে আসল দাম, স্টক, ডেলিভারি চার্জ ও মোট ফেরত দেয়।"""

    def post(self, request):
        ser = CartInput(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        result = price_cart(d["items"], d.get("coupon_code", ""), d.get("district", ""), request)
        result.pop("_coupon_obj", None)
        return Response(result)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "number"

    def get_permissions(self):
        # লগইন ছাড়াই অর্ডার করা ও নম্বর+ফোন দিয়ে ট্র্যাক করা যাবে; বাকি সব লগইন লাগবে
        if self.action in ("create", "track"):
            return [permissions.AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "items__product", "history")
        )

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "order"
        elif self.action == "track":
            self.throttle_scope = "track"
        return super().get_throttles()

    def create(self, request):
        ser = CheckoutInput(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        user = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            if user is None and SiteSetting.load().require_otp:
                row = otp_service.check_token(data.get("otp_token", ""), data["phone"])
                row.consumed = True  # একটা কোডে একটাই অর্ডার
                row.save(update_fields=["consumed"])
            order = create_order(user, data, request)
        if user and data.get("save_address"):
            Address.objects.get_or_create(
                user=user, address=data["address"], district=data["district"],
                defaults={"name": data["name"], "phone": data["phone"],
                          "is_default": not Address.objects.filter(user=user).exists()},
            )
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="track")
    def track(self, request):
        """অর্ডার নম্বর + অর্ডারের মোবাইল নম্বর মিললে অর্ডারের তথ্য (গেস্ট কাস্টমারের জন্য)।"""
        try:
            phone = clean_phone(request.query_params.get("phone", ""))
        except Exception:
            return Response({"detail": "অর্ডার পাওয়া যায়নি।"}, status=404)
        order = Order.objects.filter(number=request.query_params.get("number", "").strip(), phone=phone).prefetch_related("items", "items__product", "history").first()
        if not order:
            return Response({"detail": "অর্ডার পাওয়া যায়নি।"}, status=404)
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, number=None):
        order = self.get_object()
        if order.status != Order.PENDING:
            return Response({"detail": "অর্ডার কনফার্ম হয়ে গেছে, এখন বাতিল করা যাবে না। সাপোর্টে যোগাযোগ করুন।"}, status=400)
        order = set_order_status(order, Order.CANCELLED, "কাস্টমার বাতিল করেছেন")
        return Response(OrderDetailSerializer(order).data)
