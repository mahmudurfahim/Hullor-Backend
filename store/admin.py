from django.contrib import admin

from . import models


class VariantInline(admin.TabularInline):
    model = models.ProductVariant
    extra = 0


class ImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 0


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "category", "price", "is_active", "is_featured"]
    search_fields = ["code", "name"]
    inlines = [VariantInline, ImageInline]


class ItemInline(admin.TabularInline):
    model = models.OrderItem
    extra = 0


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "customer_name", "phone", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["number", "phone", "customer_name"]
    inlines = [ItemInline]


for m in (models.Category, models.Coupon, models.Banner, models.SiteSetting, models.Review, models.WishlistItem):
    admin.site.register(m)
