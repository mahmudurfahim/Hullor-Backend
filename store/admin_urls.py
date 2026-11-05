from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import admin_views as v

router = DefaultRouter()
router.register("categories", v.AdminCategoryViewSet, basename="admin-category")
router.register("banners", v.AdminBannerViewSet, basename="admin-banner")
router.register("products", v.AdminProductViewSet, basename="admin-product")
router.register("orders", v.AdminOrderViewSet, basename="admin-order")
router.register("customers", v.AdminCustomerViewSet, basename="admin-customer")
router.register("coupons", v.AdminCouponViewSet, basename="admin-coupon")
router.register("reviews", v.AdminReviewViewSet, basename="admin-review")

urlpatterns = [
    path("dashboard/", v.AdminDashboardView.as_view()),
    path("settings/", v.AdminSettingsView.as_view()),
    path("", include(router.urls)),
]
