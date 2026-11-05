from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Banner, Category, Coupon, Order, OrderItem, Product, ProductImage, Review, SiteSetting
from .serializers import (
    AdminBannerSerializer, AdminCategorySerializer, AdminSiteSettingSerializer, AdminCouponSerializer, AdminCustomerSerializer,
    AdminImageSerializer, AdminProductSerializer, AdminReviewSerializer, OrderDetailSerializer,
    OrderListSerializer, SiteSettingSerializer,
)
from .services import set_order_status

User = get_user_model()
CLOSED = [Order.CANCELLED, Order.RETURNED]


class AdminOnly(permissions.IsAdminUser):
    pass


class AdminBase:
    permission_classes = [AdminOnly]
    throttle_classes = []


class AdminCategoryViewSet(AdminBase, viewsets.ModelViewSet):
    serializer_class = AdminCategorySerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None

    def get_queryset(self):
        return Category.objects.annotate(product_count=Count("products"))


class AdminBannerViewSet(AdminBase, viewsets.ModelViewSet):
    serializer_class = AdminBannerSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Banner.objects.all()
    pagination_class = None


class AdminProductViewSet(AdminBase, viewsets.ModelViewSet):
    serializer_class = AdminProductSerializer

    def get_queryset(self):
        qs = Product.objects.select_related("category").prefetch_related("images", "variants")
        p = self.request.query_params
        if p.get("search"):
            qs = qs.filter(Q(name__icontains=p["search"]) | Q(code__icontains=p["search"]))
        if p.get("category"):
            qs = qs.filter(category_id=p["category"])
        if p.get("is_active") in ("0", "1"):
            qs = qs.filter(is_active=p["is_active"] == "1")
        if p.get("stock") in ("low", "out"):
            qs = qs.annotate(total_stock=Coalesce(Sum("variants__stock"), 0, output_field=IntegerField()))
            qs = qs.filter(total_stock__lte=5 if p["stock"] == "low" else 0)
        return qs

    @action(detail=True, methods=["post"], url_path="images", parser_classes=[MultiPartParser, FormParser, JSONParser])
    def add_images(self, request, pk=None):
        product = self.get_object()
        files = request.FILES.getlist("image") or request.FILES.getlist("images")
        url = (request.data.get("url") or "").strip() if hasattr(request.data, "get") else ""
        if not files and not url:
            return Response({"detail": "ছবি বা ছবির URL দিন।"}, status=400)
        pos = product.images.count()
        created = []
        validator = serializers.ImageField()
        for f in files:
            if f.size > 6 * 1024 * 1024:
                return Response({"detail": f"{f.name}: ছবি ৬MB এর বেশি বড়।"}, status=400)
            try:
                validator.run_validation(f)
            except serializers.ValidationError:
                return Response({"detail": f"{f.name} সঠিক ছবি নয়।"}, status=400)
            created.append(ProductImage.objects.create(product=product, image=f, position=pos))
            pos += 1
        if url:
            created.append(ProductImage.objects.create(product=product, url=url, position=pos))
        return Response(AdminImageSerializer(created, many=True, context={"request": request}).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>\d+)")
    def delete_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        img = product.images.filter(pk=image_id).first()
        if not img:
            return Response({"detail": "ছবি পাওয়া যায়নি।"}, status=404)
        img.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, pk=None):
        product = self.get_object()
        for pos, image_id in enumerate(request.data.get("ids", [])):
            product.images.filter(pk=image_id).update(position=pos)
        return Response(AdminImageSerializer(product.images.all(), many=True, context={"request": request}).data)


class AdminOrderViewSet(AdminBase, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def get_queryset(self):
        qs = Order.objects.select_related("user").prefetch_related("items", "items__product", "history")
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("payment_status"):
            qs = qs.filter(payment_status=p["payment_status"])
        if p.get("search"):
            s = p["search"].strip()
            qs = qs.filter(Q(number__icontains=s) | Q(phone__icontains=s) | Q(customer_name__icontains=s))
        if p.get("date_from"):
            qs = qs.filter(created_at__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(created_at__date__lte=p["date_to"])
        return qs

    def partial_update(self, request, *args, **kwargs):
        order = self.get_object()
        for f in ("customer_name", "phone", "email", "district", "address", "note"):
            if f in request.data:
                setattr(order, f, str(request.data[f]).strip())
        order.save()
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        order = self.get_object()
        order = set_order_status(order, request.data.get("status", ""), str(request.data.get("note", "")))
        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order).data)

    @action(detail=False, methods=["get"])
    def counts(self, request):
        rows = Order.objects.values("status").annotate(n=Count("id"))
        data = {s: 0 for s, _ in Order.STATUS_CHOICES}
        data.update({r["status"]: r["n"] for r in rows})
        data["all"] = sum(data.values())
        return Response(data)


class AdminCustomerViewSet(AdminBase, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminCustomerSerializer

    def get_queryset(self):
        qs = User.objects.annotate(
            orders_count=Count("orders", distinct=True),
            total_spent=Coalesce(Sum("orders__total", filter=~Q(orders__status__in=CLOSED)), 0, output_field=IntegerField()),
        ).order_by("-date_joined")
        s = self.request.query_params.get("search")
        if s:
            qs = qs.filter(Q(name__icontains=s) | Q(phone__icontains=s) | Q(email__icontains=s))
        return qs

    @action(detail=True, methods=["post"])
    def toggle_active(self, request, pk=None):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "নিজের অ্যাকাউন্ট বন্ধ করা যাবে না।"}, status=400)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return Response(self.get_serializer(self.get_queryset().get(pk=user.pk)).data)

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        qs = Order.objects.filter(user_id=pk).prefetch_related("items")
        return Response(OrderListSerializer(qs[:50], many=True).data)


class AdminCouponViewSet(AdminBase, viewsets.ModelViewSet):
    serializer_class = AdminCouponSerializer
    queryset = Coupon.objects.all()
    pagination_class = None


class AdminReviewViewSet(AdminBase, mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminReviewSerializer
    queryset = Review.objects.select_related("user", "product")
    http_method_names = ["get", "patch", "delete", "head", "options"]


class AdminSettingsView(AdminBase, APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(AdminSiteSettingSerializer(SiteSetting.load(), context={"request": request}).data)

    def patch(self, request):
        ser = AdminSiteSettingSerializer(SiteSetting.load(), data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class AdminDashboardView(AdminBase, APIView):
    def get(self, request):
        now = timezone.localtime()
        today = now.date()
        valid = Order.objects.exclude(status__in=CLOSED)

        def agg(qs):
            r = qs.aggregate(n=Count("id"), s=Coalesce(Sum("total"), 0, output_field=IntegerField()))
            return r["n"], r["s"]

        orders_today, revenue_today = agg(valid.filter(created_at__date=today))
        orders_month, revenue_month = agg(valid.filter(created_at__year=today.year, created_at__month=today.month))
        orders_total, revenue_total = agg(valid)
        _, revenue_delivered = agg(Order.objects.filter(status=Order.DELIVERED))

        start = today - timedelta(days=13)
        rows = (
            valid.filter(created_at__date__gte=start)
            .annotate(d=TruncDate("created_at"))
            .values("d").annotate(orders=Count("id"), revenue=Sum("total"))
        )
        by_day = {r["d"]: r for r in rows}
        sales = []
        for i in range(14):
            d = start + timedelta(days=i)
            r = by_day.get(d)
            sales.append({"date": d.isoformat(), "orders": r["orders"] if r else 0, "revenue": r["revenue"] if r else 0})

        stock = (
            Product.objects.filter(is_active=True)
            .annotate(total_stock=Coalesce(Sum("variants__stock"), 0, output_field=IntegerField()))
            .filter(total_stock__lte=5).order_by("total_stock")[:8]
        )
        top = (
            OrderItem.objects.exclude(order__status__in=CLOSED)
            .values("name", "code").annotate(qty=Sum("quantity")).order_by("-qty")[:5]
        )
        status_counts = {s: 0 for s, _ in Order.STATUS_CHOICES}
        for r in Order.objects.values("status").annotate(n=Count("id")):
            status_counts[r["status"]] = r["n"]
        recent = Order.objects.prefetch_related("items")[:8]

        return Response({
            "orders_today": orders_today, "revenue_today": revenue_today,
            "orders_month": orders_month, "revenue_month": revenue_month,
            "orders_total": orders_total, "revenue_total": revenue_total, "revenue_delivered": revenue_delivered,
            "pending_orders": status_counts[Order.PENDING],
            "customers": User.objects.filter(is_staff=False).count(),
            "products": Product.objects.count(), "active_products": Product.objects.filter(is_active=True).count(),
            "sales_by_day": sales, "status_counts": status_counts,
            "low_stock": [{"id": p.id, "name": p.name, "code": p.code, "stock": p.total_stock} for p in stock],
            "top_products": list(top),
            "recent_orders": OrderListSerializer(recent, many=True).data,
        })
