from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.serializers import clean_phone
from .models import (
    Banner, Category, Coupon, Order, OrderItem, OrderStatusHistory, Product, ProductImage,
    ProductVariant, Review, SiteSetting,
)
from .lang import LangFieldsMixin, request_lang
from .utils import file_url, product_image_urls


# ------------------------------------------------------------------ public catalog
class SiteSettingSerializer(LangFieldsMixin, serializers.ModelSerializer):
    """পাবলিক (স্টোরফ্রন্ট) — ?lang=en হলে English লেখা, খালি থাকলে বাংলাটাই।"""

    lang_fields = ("tagline", "announcement", "address", "about_title", "about_text")
    about_image = serializers.SerializerMethodField()

    class Meta:
        model = SiteSetting
        fields = [
            "store_name", "tagline", "phone", "whatsapp", "email", "address", "announcement",
            "facebook_url", "instagram_url", "delivery_charge_dhaka", "delivery_charge_outside", "free_delivery_above",
            "about_image", "about_title", "about_text",
        ]

    def get_about_image(self, obj):
        return file_url(obj.about_image, obj.about_image_url, self.context.get("request"))


class AdminSiteSettingSerializer(serializers.ModelSerializer):
    """অ্যাডমিন প্যানেল — বাংলা ও English দুটো ফিল্ডই আসল মানে।"""

    about_image_src = serializers.SerializerMethodField()
    remove_about_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = SiteSetting
        fields = [
            "store_name", "tagline", "tagline_en", "phone", "whatsapp", "email", "address", "address_en",
            "announcement", "announcement_en", "facebook_url", "instagram_url",
            "delivery_charge_dhaka", "delivery_charge_outside", "free_delivery_above",
            "about_image", "about_image_url", "about_image_src", "remove_about_image",
            "about_title", "about_title_en", "about_text", "about_text_en", "require_otp",
        ]
        extra_kwargs = {"about_image": {"required": False, "write_only": True}, "about_image_url": {"required": False, "allow_blank": True}}

    def get_about_image_src(self, obj):
        return file_url(obj.about_image, obj.about_image_url, self.context.get("request"))

    def validate_about_image(self, f):
        if f and f.size > 6 * 1024 * 1024:
            raise serializers.ValidationError("ছবির সাইজ ৬MB এর বেশি হতে পারবে না।")
        return f

    def update(self, instance, validated):
        if validated.pop("remove_about_image", False):
            instance.about_image = None
            validated["about_image_url"] = ""
        validated.pop("remove_about_image", None)
        return super().update(instance, validated)


class CategorySerializer(LangFieldsMixin, serializers.ModelSerializer):
    lang_fields = ("name",)
    image = serializers.SerializerMethodField()
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "image", "product_count"]

    def get_image(self, obj):
        return file_url(obj.image, obj.image_url, self.context.get("request"))


class BannerSerializer(LangFieldsMixin, serializers.ModelSerializer):
    lang_fields = ("title", "subtitle", "button_text")
    image = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ["id", "title", "subtitle", "button_text", "link", "image"]

    def get_image(self, obj):
        return file_url(obj.image, obj.image_url, self.context.get("request"))


class ProductListSerializer(LangFieldsMixin, serializers.ModelSerializer):
    lang_fields = ("name",)
    category = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    image2 = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    rating_avg = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "code", "category", "price", "old_price", "discount_percent", "image", "image2",
            "in_stock", "is_featured", "sizes", "colors", "rating_avg", "rating_count", "created_at",
        ]

    def _images(self, obj):
        return product_image_urls(obj, self.context.get("request"))

    def get_category(self, obj):
        if not obj.category_id:
            return None
        name = obj.category.name
        if request_lang(self.context.get("request")) == "en" and (obj.category.name_en or "").strip():
            name = obj.category.name_en
        return {"id": obj.category_id, "name": name, "slug": obj.category.slug}

    def get_image(self, obj):
        imgs = self._images(obj)
        return imgs[0] if imgs else None

    def get_image2(self, obj):
        imgs = self._images(obj)
        return imgs[1] if len(imgs) > 1 else None

    def get_in_stock(self, obj):
        return any(v.stock > 0 for v in obj.variants.all())

    def get_sizes(self, obj):
        seen = []
        for v in obj.variants.all():
            if v.size not in seen:
                seen.append(v.size)
        return seen

    def get_colors(self, obj):
        seen, out = set(), []
        for v in obj.variants.all():
            if v.color and v.color not in seen:
                seen.add(v.color)
                out.append({"name": v.color, "hex": v.color_hex})
        return out

    def get_rating_avg(self, obj):
        val = getattr(obj, "rating_avg", None)
        return round(val, 1) if val else 0

    def get_rating_count(self, obj):
        return getattr(obj, "rating_count", 0) or 0


class VariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "color_hex", "stock"]


class ProductDetailSerializer(ProductListSerializer):
    lang_fields = ("name", "description")
    images = serializers.SerializerMethodField()
    variants = VariantSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["description", "fabric", "fit", "care", "images", "variants"]

    def get_images(self, obj):
        return self._images(obj)


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "user_name", "rating", "comment", "created_at"]

    def get_user_name(self, obj):
        name = obj.user.name or "গ্রাহক"
        return name.split()[0] + (" " + name.split()[1][0] + "." if len(name.split()) > 1 else "")


# ------------------------------------------------------------------ cart / checkout
class CartItemInput(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=50)


class CartInput(serializers.Serializer):
    items = CartItemInput(many=True, allow_empty=False, max_length=40)
    coupon_code = serializers.CharField(required=False, allow_blank=True, max_length=30)
    district = serializers.CharField(required=False, allow_blank=True, max_length=60)


class CheckoutInput(CartInput):
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    district = serializers.CharField(max_length=60)
    address = serializers.CharField(max_length=500)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    save_address = serializers.BooleanField(required=False, default=False)
    otp_token = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_phone(self, value):
        return clean_phone(value)

    def validate_address(self, value):
        value = value.strip()
        if len(value) < 8:
            raise serializers.ValidationError("পূর্ণ ঠিকানা লিখুন (বাসা/রোড/এলাকা)।")
        return value


# ------------------------------------------------------------------ orders
class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.IntegerField(read_only=True)
    slug = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "name", "code", "size", "color", "price", "quantity", "image", "line_total", "slug"]

    def get_slug(self, obj):
        return obj.product.slug if obj.product_id else None


class HistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["status", "note", "created_at"]


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    thumb = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "number", "status", "payment_status", "payment_method", "customer_name", "phone", "district",
            "total", "created_at", "items_count", "thumb",
        ]

    def get_items_count(self, obj):
        return sum(i.quantity for i in obj.items.all())

    def get_thumb(self, obj):
        first = next(iter(obj.items.all()), None)
        return first.image if first and first.image else None


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    history = HistorySerializer(many=True, read_only=True)
    customer = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "number", "status", "payment_method", "payment_status", "customer_name", "phone", "email",
            "district", "address", "note", "subtotal", "delivery_charge", "discount", "total", "coupon_code",
            "customer_name_bn", "customer_name_en", "address_bn", "address_en", "note_bn", "note_en",
            "created_at", "updated_at", "items", "history", "customer",
        ]

    def get_customer(self, obj):
        u = obj.user
        return {"id": u.id, "name": u.name, "phone": u.phone, "email": u.email} if u else None


# ------------------------------------------------------------------ ADMIN serializers
class AdminCategorySerializer(serializers.ModelSerializer):
    image_src = serializers.SerializerMethodField()
    remove_image = serializers.BooleanField(write_only=True, required=False, default=False)
    product_count = serializers.IntegerField(read_only=True, default=0)
    slug = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Category
        fields = ["id", "name", "name_en", "slug", "image", "image_url", "image_src", "position", "is_active", "product_count", "remove_image"]
        extra_kwargs = {"image": {"required": False, "write_only": True}, "image_url": {"required": False, "allow_blank": True}}

    def get_image_src(self, obj):
        return file_url(obj.image, obj.image_url, self.context.get("request"))

    def validate_slug(self, value):
        value = value.strip()
        if value and Category.objects.filter(slug=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("এই slug আগে থেকেই আছে।")
        return value

    def update(self, instance, validated):
        if validated.pop("remove_image", False):
            instance.image = None
            validated["image_url"] = ""
        validated.pop("remove_image", None)
        return super().update(instance, validated)

    def create(self, validated):
        validated.pop("remove_image", None)
        return super().create(validated)


class AdminBannerSerializer(serializers.ModelSerializer):
    image_src = serializers.SerializerMethodField()
    remove_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Banner
        fields = ["id", "title", "title_en", "subtitle", "subtitle_en", "button_text", "button_text_en", "link", "image", "image_url", "image_src", "position", "is_active", "remove_image"]
        extra_kwargs = {"image": {"required": False, "write_only": True}, "image_url": {"required": False, "allow_blank": True}}

    def get_image_src(self, obj):
        return file_url(obj.image, obj.image_url, self.context.get("request"))

    def update(self, instance, validated):
        if validated.pop("remove_image", False):
            instance.image = None
            validated["image_url"] = ""
        validated.pop("remove_image", None)
        return super().update(instance, validated)

    def create(self, validated):
        validated.pop("remove_image", None)
        return super().create(validated)


class AdminVariantSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "color_hex", "stock"]


class AdminImageSerializer(serializers.ModelSerializer):
    src = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "src", "position"]

    def get_src(self, obj):
        return file_url(obj.image, obj.url, self.context.get("request"))


class AdminProductSerializer(serializers.ModelSerializer):
    variants = AdminVariantSerializer(many=True, required=False)
    images = AdminImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    total_stock = serializers.SerializerMethodField()
    thumb = serializers.SerializerMethodField()
    code = serializers.CharField(required=False, allow_blank=True, max_length=40)
    slug = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "name_en", "code", "slug", "category", "category_name", "description", "description_en", "fabric", "fit", "care",
            "price", "old_price", "is_active", "is_featured", "variants", "images", "total_stock", "thumb", "created_at",
        ]

    def get_total_stock(self, obj):
        return sum(v.stock for v in obj.variants.all())

    def get_thumb(self, obj):
        imgs = product_image_urls(obj, self.context.get("request"))
        return imgs[0] if imgs else None

    def validate_code(self, value):
        value = value.strip().upper()
        if value and Product.objects.filter(code=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("এই প্রোডাক্ট কোড আগেই ব্যবহার হয়েছে।")
        return value

    def validate(self, attrs):
        old, price = attrs.get("old_price"), attrs.get("price", getattr(self.instance, "price", None))
        if old is not None and price is not None and old < price:
            raise serializers.ValidationError({"old_price": "পুরনো দাম বর্তমান দামের চেয়ে কম হতে পারবে না।"})
        variants = attrs.get("variants")
        if variants is not None:
            keys = [(v["size"].strip(), (v.get("color") or "").strip()) for v in variants]
            if len(keys) != len(set(keys)):
                raise serializers.ValidationError({"variants": "একই সাইজ+কালারের ভ্যারিয়েন্ট দুইবার দেওয়া যাবে না।"})
        return attrs

    def _sync_variants(self, product, variants):
        keep = []
        for data in variants:
            vid = data.pop("id", None)
            data["size"] = data["size"].strip() or "Free"
            data["color"] = (data.get("color") or "").strip()
            obj = ProductVariant.objects.filter(pk=vid, product=product).first() if vid else None
            if obj:
                for k, v in data.items():
                    setattr(obj, k, v)
                obj.save()
            else:
                obj = ProductVariant.objects.filter(product=product, size=data["size"], color=data["color"]).first()
                if obj:
                    for k, v in data.items():
                        setattr(obj, k, v)
                    obj.save()
                else:
                    obj = ProductVariant.objects.create(product=product, **data)
            keep.append(obj.pk)
        product.variants.exclude(pk__in=keep).delete()

    def create(self, validated):
        variants = validated.pop("variants", [])
        product = Product.objects.create(**validated)
        self._sync_variants(product, variants)
        return product

    def update(self, instance, validated):
        variants = validated.pop("variants", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        if variants is not None:
            self._sync_variants(instance, variants)
        return instance


class AdminCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    is_active = serializers.BooleanField()
    is_staff = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    orders_count = serializers.IntegerField(default=0)
    total_spent = serializers.IntegerField(default=0)


class AdminCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id", "code", "discount_type", "value", "min_order", "max_discount", "usage_limit", "used_count",
            "is_active", "starts_at", "expires_at",
        ]
        read_only_fields = ["used_count"]

    def validate_code(self, value):
        value = value.strip().upper()
        if Coupon.objects.filter(code=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("এই কুপন কোড আগেই আছে।")
        return value

    def validate(self, attrs):
        if attrs.get("discount_type") == Coupon.PERCENT and attrs.get("value", 0) > 100:
            raise serializers.ValidationError({"value": "পার্সেন্ট ১০০ এর বেশি হতে পারে না।"})
        return attrs


class AdminReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "user_name", "product", "product_name", "rating", "comment", "is_approved", "created_at"]
        read_only_fields = ["product", "rating", "comment"]
