import hashlib

from django.db import migrations, models
from django.utils.text import slugify


def populate_author_slugs(apps, schema_editor):
    Author = apps.get_model("research_papers", "Author")
    used = set()

    for author in Author.objects.order_by("id").iterator(chunk_size=1000):
        base = slugify(author.name)[:300] or f"author-{author.pk}"
        candidate = base

        if candidate in used:
            digest = hashlib.sha256(author.name.encode("utf-8")).hexdigest()[:8]
            candidate = f"{base}-{digest}"
        if candidate in used:
            candidate = f"{base}-{author.pk}"

        Author.objects.filter(pk=author.pk).update(slug=candidate)
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("research_papers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="author",
            name="slug",
            field=models.SlugField(max_length=320, null=True, unique=True),
        ),
        migrations.RunPython(populate_author_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="author",
            name="slug",
            field=models.SlugField(max_length=320, unique=True),
        ),
    ]
