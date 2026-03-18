# Generated manually to update embedding dimensions from 768 to 1536

from django.db import migrations
from pgvector.django import VectorField


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0005_alter_review_user_name"),
    ]

    operations = [
        # First, clear all existing embeddings since they're incompatible
        migrations.RunSQL(
            "UPDATE tools SET embedding = NULL;",
            reverse_sql="-- No reverse operation needed",
        ),
        # Then alter the field to new dimensions
        migrations.AlterField(
            model_name="tool",
            name="embedding",
            field=VectorField(blank=True, dimensions=1536, null=True),
        ),
    ]
