from django.db import migrations, models
from django.db.migrations.operations.base import Operation


def _ensure_schema(apps, schema_editor):
    """Create the OTP schema, including when an earlier manual apply already did."""
    connection = schema_editor.connection
    user = apps.get_model("api", "User")
    code = apps.get_model("api", "EmailVerificationCode")
    tables = set(connection.introspection.table_names())
    with connection.cursor() as cursor:
        user_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, user._meta.db_table
            )
        }
    if "email_verified_at" not in user_columns:
        schema_editor.add_field(user, user._meta.get_field("email_verified_at"))
    if code._meta.db_table not in tables:
        schema_editor.create_model(code)


def _drop_schema(apps, schema_editor):
    connection = schema_editor.connection
    user = apps.get_model("api", "User")
    code = apps.get_model("api", "EmailVerificationCode")
    tables = set(connection.introspection.table_names())
    if code._meta.db_table in tables:
        schema_editor.delete_model(code)
    with connection.cursor() as cursor:
        user_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, user._meta.db_table
            )
        }
    if "email_verified_at" in user_columns:
        schema_editor.remove_field(user, user._meta.get_field("email_verified_at"))


def _state_operations():
    return [
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When this email was confirmed with a one-time code.",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="EmailVerificationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("purpose", models.CharField(default="tool_submit", max_length=32)),
                ("code_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "email_verification_codes",
                "indexes": [
                    models.Index(
                        fields=["email", "purpose", "-created_at"],
                        name="email_code_email_purpose_idx",
                    ),
                    models.Index(
                        fields=["ip_address", "-created_at"],
                        name="email_code_ip_created_idx",
                    ),
                ],
            },
        ),
    ]


class EnsureEmailOtpSchema(Operation):
    def state_forwards(self, app_label, state):
        for operation in _state_operations():
            operation.state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        _ensure_schema(to_state.apps, schema_editor)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        _drop_schema(from_state.apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_growth_discovery_events"),
    ]

    operations = [
        EnsureEmailOtpSchema(),
    ]
