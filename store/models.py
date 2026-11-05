import random
import string
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def _unique_slug(model, base, instance_pk=None, fallback="item"):
    base = slugify(base or "", allow_unicode=True)[:90] or f"{fallback}-{uuid.uuid4().hex[:6]}"
    slug, n = base, 2
    qs = model.objects.all()
    if instance_pk:
        qs = qs.exclude(pk=instance_pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class SiteSetting(models.Model):
    """একটাই row (pk=1). Admin panel থেকে এডিট হয়।"""

    store_name = models.CharField(max_length=80, default="HULLOR")
    tagline = models.CharField(max_length=160, default="Stay true to your style.")
    phone = models.CharField(max_length=20, default="01863709122")
    whatsapp = models.CharField(max_length=20, default="8801863709122", help_text="88 সহ, শুরুতে + ছাড়া")
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    announcement = models.CharField(max_length=200, blank=True, default="সারা বাংলাদেশে ক্যাশ অন ডেলিভারি", help_text="বাংলা")
    # --- English সংস্করণ (খালি থাকলে English সাইটেও বাংলা লেখাটাই দেখাবে) ---
    tagline_en = models.CharField(max_length=160, blank=True, default="Stay true to your style.")
    announcement_en = models.CharField(max_length=200, blank=True, default="Cash on delivery across Bangladesh")
    address_en = models.CharField(max_length=255, blank=True)
    # --- About us ---
    about_image = models.ImageField(upload_to="site/", blank=True)
    about_image_url = models.CharField(max_length=500, blank=True)
    about_title = models.CharField(max_length=160, blank=True)
    about_title_en = models.CharField(max_length=160, blank=True)
    about_text = models.TextField(blank=True, help_text="প্যারাগ্রাফ আলাদা করতে ফাঁকা লাইন দিন")
    about_text_en = models.TextField(blank=True)
    # --- Checkout ---
    require_otp = models.BooleanField(default=True, help_text="লগইন ছাড়া অর্ডারে মোবাইল নম্বর OTP দিয়ে যাচাই")
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    delivery_charge_dhaka = models.PositiveIntegerField(default=0)
    delivery_charge_outside = models.PositiveIntegerField(default=0)
    free_delivery_above = models.PositiveIntegerField(null=True, blank=True, help_text="এই টাকার উপরে অর্ডারে ডেলিভারি ফ্রি (খালি = কখনো না)")

    class Meta:
        verbose_name = "site setting"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Site settings"


class Category(models.Model):
    name = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)
    slug = models.SlugField(max_length=100, unique=True, allow_unicode=True, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(Category, self.name, self.pk, "cat")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    name = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    code = models.CharField(max_length=40, unique=True, blank=True, help_text="কাস্টমার-ফেসিং প্রোডাক্ট কোড (যেমন FMSH001)")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    fabric = models.CharField(max_length=160, blank=True)
    fit = models.CharField(max_length=160, blank=True)
    care = models.CharField(max_length=255, blank=True)
    price = models.PositiveIntegerField()
    old_price = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        if not self.code:
            while True:
                candidate = "HL" + "".join(random.choices(string.digits, k=5))
                if not Product.objects.filter(code=candidate).exists():
                    self.code = candidate
                    break
        if not self.slug:
            self.slug = _unique_slug(Product, self.code, self.pk, "p")
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) * 100 / self.old_price)
        return 0

    def __str__(self):
        return f"{self.code} - {self.name}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True)
    url = models.CharField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=30, default="Free")
    color = models.CharField(max_length=40, blank=True)
    color_hex = models.CharField(max_length=9, blank=True)
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["product", "size", "color"], name="uniq_variant")]

    def __str__(self):
        return f"{self.product.code} {self.size} {self.color}".strip()


class Banner(models.Model):
    title = models.CharField(max_length=140)
    title_en = models.CharField(max_length=140, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    subtitle_en = models.CharField(max_length=255, blank=True)
    button_text = models.CharField(max_length=40, blank=True, default="কালেকশন দেখুন")
    button_text_en = models.CharField(max_length=40, blank=True, default="Shop now")
    link = models.CharField(max_length=255, blank=True, default="/shop")
    image = models.ImageField(upload_to="banners/", blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]


class Coupon(models.Model):
    PERCENT, FIXED = "percent", "fixed"
    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=10, choices=[(PERCENT, "Percent"), (FIXED, "Fixed")], default=PERCENT)
    value = models.PositiveIntegerField()
    min_order = models.PositiveIntegerField(default=0)
    max_discount = models.PositiveIntegerField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def evaluate(self, subtotal):
        """(discount, error_message)"""
        now = timezone.now()
        if not self.is_active:
            return 0, "এই কুপনটি এখন সক্রিয় নেই।"
        if self.starts_at and now < self.starts_at:
            return 0, "এই কুপনটি এখনও শুরু হয়নি।"
        if self.expires_at and now > self.expires_at:
            return 0, "কুপনের মেয়াদ শেষ হয়ে গেছে।"
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return 0, "এই কুপনের ব্যবহারের সীমা শেষ।"
        if subtotal < self.min_order:
            return 0, f"এই কুপনের জন্য সর্বনিম্ন অর্ডার ৳{self.min_order}।"
        if self.discount_type == self.PERCENT:
            discount = subtotal * min(self.value, 100) // 100
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = self.value
        return min(discount, subtotal), None

    def __str__(self):
        return self.code


class Order(models.Model):
    PENDING, CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED, RETURNED = (
        "pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "returned",
    )
    STATUS_CHOICES = [
        (PENDING, "Pending"), (CONFIRMED, "Confirmed"), (PROCESSING, "Processing"),
        (SHIPPED, "Shipped"), (DELIVERED, "Delivered"), (CANCELLED, "Cancelled"), (RETURNED, "Returned"),
    ]
    ACTIVE_FLOW = [PENDING, CONFIRMED, PROCESSING, SHIPPED, DELIVERED]

    number = models.CharField(max_length=24, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="orders")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    payment_method = models.CharField(max_length=10, default="cod")
    payment_status = models.CharField(max_length=10, choices=[("unpaid", "Unpaid"), ("paid", "Paid")], default="unpaid")
    customer_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    district = models.CharField(max_length=60)
    address = models.TextField()
    note = models.TextField(blank=True)
    # কাস্টমার যে ভাষায় লিখেছেন সেই ভাষার ফিল্ডে সেভ হয় (বাংলা অক্ষর থাকলে _bn, নাহলে _en); অন্যটা খালি থাকে।
    customer_name_bn = models.CharField(max_length=120, blank=True)
    customer_name_en = models.CharField(max_length=120, blank=True)
    address_bn = models.TextField(blank=True)
    address_en = models.TextField(blank=True)
    note_bn = models.TextField(blank=True)
    note_en = models.TextField(blank=True)
    subtotal = models.PositiveIntegerField(default=0)
    delivery_charge = models.PositiveIntegerField(default=0)
    discount = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    coupon_code = models.CharField(max_length=30, blank=True)
    stock_restored = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if not self.number:
            for _ in range(20):
                candidate = f"HL-{timezone.localtime().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
                if not Order.objects.filter(number=candidate).exists():
                    self.number = candidate
                    break
            else:
                self.number = f"HL-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL, related_name="order_items")
    variant = models.ForeignKey(ProductVariant, null=True, on_delete=models.SET_NULL, related_name="order_items")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    size = models.CharField(max_length=30, blank=True)
    color = models.CharField(max_length=40, blank=True)
    price = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    image = models.CharField(max_length=500, blank=True)

    @property
    def line_total(self):
        return self.price * self.quantity


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    status = models.CharField(max_length=12)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="uniq_wish")]


class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="uniq_review")]


class PhoneOTP(models.Model):
    """মোবাইল নম্বর যাচাইয়ের OTP (কোড সরাসরি রাখা হয় না, শুধু hash)।"""

    phone = models.CharField(max_length=15, db_index=True)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed = models.BooleanField(default=False)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone} @ {self.created_at:%Y-%m-%d %H:%M}"
