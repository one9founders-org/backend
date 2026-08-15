from django.db import migrations

ORPHAN_COLUMNS = (
    "api_docs_quality",
    "compliance_certs",
    "data_residency",
    "employee_count_range",
    "encryption_standard",
    "free_tier_limits",
    "funding_status",
    "has_startup_program",
    "hq_country",
    "learning_curve",
    "time_to_first_value",
)


FORWARDS = """
DO $$
DECLARE
  col text;
  cols text[] := ARRAY[{cols}];
BEGIN
  FOREACH col IN ARRAY cols
  LOOP
    IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'tools'
        AND column_name = col
        AND is_nullable = 'NO'
    ) THEN
      EXECUTE format(
        'ALTER TABLE tools ALTER COLUMN %I DROP NOT NULL',
        col
      );
    END IF;
  END LOOP;
END $$;
""".format(
    cols=", ".join(f"'{name}'" for name in ORPHAN_COLUMNS)
)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0020_tool_entry_type_tool_hygiene_flags_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARDS, reverse_sql=migrations.RunSQL.noop),
    ]
