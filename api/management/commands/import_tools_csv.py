"""
Import Tools from CSV Management Command
"""

import csv
import json
import logging
from decimal import Decimal
from unittest.mock import patch

from django.core.management.base import BaseCommand
from django.db import models
from django.utils.text import slugify

from api.models import Category, Tool

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import tools from a CSV file (avoids duplicates, bulk handles 26k+ rows)"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        csv_file = options["csv_file"]

        try:

            def no_ai_save(self_instance, *save_args, **save_kwargs):
                models.Model.save(self_instance, *save_args, **save_kwargs)

            with patch("api.models.Tool.save", new=no_ai_save):
                with open(csv_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    created_count = 0
                    updated_count = 0

                    for i, row in enumerate(reader, start=1):
                        name = row.get("name", "").strip()
                        if not name:
                            continue

                        slug = row.get("slug", "").strip() or slugify(name)

                        def parse_json_array(val):
                            if not val:
                                return []
                            try:
                                return json.loads(val)
                            except json.JSONDecodeError:
                                return [v.strip() for v in val.split(",") if v.strip()]

                        tags = parse_json_array(row.get("tags"))
                        use_cases = parse_json_array(row.get("use_cases"))
                        features = parse_json_array(row.get("features"))
                        platforms = parse_json_array(row.get("platforms"))
                        ideal_for = parse_json_array(row.get("ideal_for"))
                        integrations = parse_json_array(row.get("integrations"))
                        pricing_models = parse_json_array(row.get("pricing_models"))
                        pricing_tiers = parse_json_array(row.get("pricing_tiers"))

                        def safe_decimal(val):
                            try:
                                return Decimal(val) if val else None
                            except Exception:
                                return None

                        def safe_int(val):
                            try:
                                return int(float(val)) if val else 0
                            except Exception:
                                return 0

                        def safe_bool(val):
                            val_str = str(val).lower().strip()
                            return val_str in ["true", "1", "t", "y", "yes"]

                        tool_defaults = {
                            "name": name,
                            "short_description": row.get("short_description", "")[:200],
                            "description": row.get("description", ""),
                            "website": row.get("website", ""),
                            "affiliate_url": row.get("affiliate_url", ""),
                            "logo_url": row.get("logo_url", ""),
                            "video_demo_url": row.get("video_demo_url", ""),
                            "pricing_from": safe_decimal(row.get("pricing_from")),
                            "free_tier_available": safe_bool(
                                row.get("free_tier_available", False)
                            ),
                            "free_trial_days": safe_int(row.get("free_trial_days")),
                            "tags": tags,
                            "use_cases": use_cases,
                            "integrations": integrations,
                            "features": features,
                            "platforms": platforms,
                            "startup_benefits": row.get("startup_benefits", ""),
                            "ideal_for": ideal_for,
                            "rating": safe_decimal(row.get("rating")) or Decimal("0.0"),
                            "review_count": safe_int(row.get("review_count")),
                            "views_count": safe_int(row.get("views_count")),
                            "startup_friendly": safe_bool(
                                row.get("startup_friendly", False)
                            ),
                            "verified": safe_bool(row.get("verified", False)),
                            "is_featured": safe_bool(row.get("is_featured", False)),
                            "is_active": safe_bool(row.get("is_active", True)),
                            "pricing_models": pricing_models,
                            "pricing_tiers": pricing_tiers,
                        }

                        tool = Tool.objects.filter(slug=slug).first()
                        if not tool:
                            tool = Tool.objects.filter(name=name).first()

                        if tool:
                            tool_defaults.pop("name", None)
                            tool_defaults.pop("slug", None)
                            for k, v in tool_defaults.items():
                                setattr(tool, k, v)
                            tool.save()
                            updated_count += 1
                        else:
                            tool = Tool(slug=slug, **tool_defaults)
                            tool.save()
                            created_count += 1

                        cat_field = row.get("categories", "")
                        cat_names = parse_json_array(cat_field)
                        if cat_names:
                            cat_objs = []
                            for cname in cat_names:
                                cat_slug = slugify(cname)
                                category, _ = Category.objects.get_or_create(
                                    slug=cat_slug, defaults={"name": cname}
                                )
                                cat_objs.append(category)
                            tool.categories.set(cat_objs)

                        if i % 1000 == 0:
                            self.stdout.write(f"Processed {i} tools...")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed CSV."
                    f" Created: {created_count}, Updated: {updated_count}"
                )
            )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error processing CSV: {e}"))
            import traceback

            traceback.print_exc()
