import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthLoginSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("client_id", models.CharField(max_length=128)),
                ("redirect_uri", models.TextField()),
                ("state", models.CharField(max_length=256)),
                ("code_challenge", models.CharField(max_length=128)),
                ("code_challenge_method", models.CharField(default="S256", max_length=16)),
                ("audience", models.CharField(blank=True, default="", max_length=256)),
                ("scope", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
            ],
            options={
                "indexes": [
                    models.Index(fields=["expires_at"], name="coworker_cl_expires_0f0c0c_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuthorizationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("code", models.CharField(max_length=128, unique=True)),
                ("client_id", models.CharField(max_length=128)),
                ("redirect_uri", models.TextField()),
                ("code_challenge", models.CharField(max_length=128)),
                ("code_challenge_method", models.CharField(default="S256", max_length=16)),
                ("scope", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CloudConnection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("provider", models.CharField(max_length=64)),
                ("connector", models.CharField(max_length=64)),
                ("status", models.CharField(default="connected", max_length=32)),
                ("account", models.CharField(blank=True, default="", max_length=255)),
                ("account_id", models.CharField(blank=True, default="", max_length=255)),
                ("scope", models.TextField(blank=True, default="")),
                ("refresh_token", models.TextField(blank=True, default="")),
                ("access_token", models.TextField(blank=True, default="")),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("tenant_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cloud_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["user", "connector"], name="coworker_cl_user_id_7a1f2a_idx"
                    ),
                    models.Index(
                        fields=["user", "status"], name="coworker_cl_user_id_2b9c1d_idx"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ManagedOAuthPending",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("provider", models.CharField(max_length=64)),
                ("connector", models.CharField(max_length=64)),
                ("app_state", models.CharField(max_length=128)),
                ("sidecar_redirect", models.TextField()),
                ("access", models.CharField(blank=True, default="", max_length=64)),
                ("flow", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
