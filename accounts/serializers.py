from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Address
from .utils import normalize_phone

User = get_user_model()


def clean_phone(value):
    try:
        return normalize_phone(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages[0])


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "phone", "email", "is_staff", "date_joined"]
        read_only_fields = ["id", "phone", "is_staff", "date_joined"]


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("নাম লিখুন।")
        return value

    def validate_phone(self, value):
        phone = clean_phone(value)
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("এই মোবাইল নম্বর দিয়ে আগেই অ্যাকাউন্ট খোলা আছে।")
        return phone

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("এই ইমেইল দিয়ে আগেই অ্যাকাউন্ট খোলা আছে।")
        return value or None

    def create(self, validated):
        return User.objects.create_user(
            phone=validated["phone"],
            password=validated["password"],
            name=validated["name"],
            email=validated.get("email"),
        )


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField()  # মোবাইল নম্বর অথবা ইমেইল
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        ident = attrs["identifier"].strip()
        user = None
        if "@" in ident:
            user = User.objects.filter(email__iexact=ident).first()
        else:
            try:
                user = User.objects.filter(phone=normalize_phone(ident)).first()
            except DjangoValidationError:
                user = None
        if not user or not user.check_password(attrs["password"]):
            raise serializers.ValidationError({"detail": "মোবাইল/ইমেইল অথবা পাসওয়ার্ড ভুল।"})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "এই অ্যাকাউন্টটি বন্ধ করা আছে।"})
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=6, max_length=128)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "label", "name", "phone", "district", "address", "is_default"]

    def validate_phone(self, value):
        return clean_phone(value)
