from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["phone", "name", "email", "is_staff", "is_active", "date_joined"]
    search_fields = ["phone", "name", "email"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Info", {"fields": ("name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "name", "password1", "password2")}),)


admin.site.register(Address)
