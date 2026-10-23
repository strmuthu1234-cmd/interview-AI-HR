from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "is_active", "last_login", "date_joined"]
        read_only_fields = ["id", "last_login", "date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "password"]
        read_only_fields = ["id"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        pw = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(pw)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "role", "is_active", "password"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def update(self, instance, validated_data):
        pw = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if pw:
            instance.set_password(pw)
        instance.save()
        return instance


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.organization_id:
            raise serializers.ValidationError("This account is not attached to an organisation.")
        data["user"] = UserSerializer(self.user).data
        return data


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ["id", "action", "entity_type", "entity_id", "actor_name", "metadata", "ip_address", "created_at"]

    def get_actor_name(self, obj):
        return obj.actor.get_username() if obj.actor else obj.actor_label
