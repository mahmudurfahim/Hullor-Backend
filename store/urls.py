from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("orders", views.OrderViewSet, basename="order")

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("settings/", views.SettingsView.as_view()),
    path("banners/", views.BannerListView.as_view()),
    path("categories/", views.CategoryListView.as_view()),
    path("wishlist/", views.WishlistView.as_view()),
    path("cart/validate/", views.CartValidateView.as_view()),
    path("otp/send/", views.OtpSendView.as_view()),
    path("otp/verify/", views.OtpVerifyView.as_view()),
    path("", include(router.urls)),
]
