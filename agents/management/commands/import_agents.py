import json
import logging

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from agents.models import AgentCategory, AIAgent

logger = logging.getLogger(__name__)


def label_to_slug(label):
    """Convert a category label to a slug."""
    return slugify(label)


def split_pipe_delimited(value):
    """Split a pipe-delimited string into a list. Return empty list for empty/None."""
    if not value or not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(" || ") if item.strip()]


def safe_int(value, default=0):
    """Safely convert a value to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    """Safely convert a value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value, default=False):
    """Safely convert a value to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def safe_str(value, default=""):
    """Safely convert a value to string, handling None."""
    if value is None:
        return default
    return str(value).strip()


class Command(BaseCommand):
    help = "Import AI agents and categories from JSON seed files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--agents",
            type=str,
            required=True,
            help="Path to agents_full.json",
        )
        parser.add_argument(
            "--categories",
            type=str,
            required=True,
            help="Path to categories.json",
        )

    def handle(self, *args, **options):
        agents_path = options["agents"]
        categories_path = options["categories"]

        # Step 1: Import categories
        self.import_categories(categories_path)

        # Step 2: Import agents
        self.import_agents(agents_path)

        # Step 3: Update category agent counts
        self.update_category_counts()

    def import_categories(self, path):
        self.stdout.write("Importing categories...")

        with open(path, "r") as f:
            categories_data = json.load(f)

        # Build lookup of existing categories by slug
        existing = {c.slug: c for c in AgentCategory.objects.all()}

        to_create = []
        to_update = []
        created_count = 0
        updated_count = 0

        for item in categories_data:
            slug = item.get("slug", "")
            if not slug:
                continue

            defaults = {
                "label": safe_str(item.get("label", "")),
                "agent_count": safe_int(item.get("agent_count")),
                "growth_rate": safe_float(item.get("growth_rate")),
                "new_agents_30d": safe_int(item.get("new_agents_30d")),
            }

            if slug in existing:
                cat = existing[slug]
                for key, val in defaults.items():
                    setattr(cat, key, val)
                to_update.append(cat)
                updated_count += 1
            else:
                to_create.append(AgentCategory(slug=slug, **defaults))
                created_count += 1

        if to_create:
            AgentCategory.objects.bulk_create(to_create, batch_size=200)
        if to_update:
            AgentCategory.objects.bulk_update(
                to_update,
                ["label", "agent_count", "growth_rate", "new_agents_30d"],
                batch_size=200,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created_count} categories, "
                f"updated {updated_count} categories"
            )
        )

    def import_agents(self, path):
        self.stdout.write("Importing agents...")

        with open(path, "r") as f:
            agents_data = json.load(f)

        # Build category lookup by slug
        cat_lookup = {c.slug: c for c in AgentCategory.objects.all()}

        # Build existing agents lookup by slug
        existing = {a.slug: a for a in AIAgent.objects.all()}

        to_create = []
        to_update = []
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for item in agents_data:
            slug = safe_str(item.get("slug", ""))
            name = safe_str(item.get("name", ""))

            if not slug or not name:
                skipped_count += 1
                continue

            # Map category label to AgentCategory
            category_label = safe_str(item.get("category", ""))
            category_slug = label_to_slug(category_label) if category_label else ""
            category = cat_lookup.get(category_slug)

            # Parse pipe-delimited fields
            key_features = split_pipe_delimited(item.get("keyFeatures"))
            use_cases = split_pipe_delimited(item.get("useCases"))

            agent_data = {
                "external_id": safe_str(item.get("id")),
                "name": name,
                "category": category,
                "category_name": category_label,
                "industry": safe_str(item.get("industry", "")),
                "access": safe_str(item.get("access", "")),
                "pricing_model": safe_str(item.get("pricingModel", "")),
                "short_description": safe_str(item.get("shortDescription", "")),
                "long_description": safe_str(item.get("longDescription", "")),
                "key_features": key_features,
                "use_cases": use_cases,
                "logo_url": safe_str(item.get("logo", "")),
                "image_url": safe_str(item.get("image", "")),
                "video_url": safe_str(item.get("video", "")),
                "popularity_score": safe_int(item.get("popularityScore")),
                "upvotes": safe_int(item.get("upvotes")),
                "views": safe_int(item.get("views")),
                "bookmark_count": safe_int(item.get("bookmarkCount")),
                "review_count": safe_int(item.get("reviewCount")),
                "average_rating": safe_float(item.get("averageRating")),
                "views_24h": safe_int(item.get("views_24h")),
                "views_7d": safe_int(item.get("views_7d")),
                "views_30d": safe_int(item.get("views_30d")),
                "upvotes_24h": safe_int(item.get("upvotes_24h")),
                "upvotes_7d": safe_int(item.get("upvotes_7d")),
                "upvotes_30d": safe_int(item.get("upvotes_30d")),
                "website": safe_str(item.get("website", "")),
                "github_url": safe_str(item.get("githubUrl", "")),
                "twitter_url": safe_str(item.get("twitterUrl", "")),
                "linkedin_url": safe_str(item.get("linkedinUrl", "")),
                "discord_url": safe_str(item.get("discordUrl", "")),
                "email": safe_str(item.get("email", "")),
                "is_featured": safe_bool(item.get("featured")),
                "seo_boost": safe_bool(item.get("seoBoost")),
            }

            # Parse created_at
            created_at_str = item.get("createdAt")
            if created_at_str:
                parsed = parse_datetime(created_at_str)
                if parsed:
                    agent_data["created_at"] = parsed

            if slug in existing:
                agent = existing[slug]
                for key, val in agent_data.items():
                    setattr(agent, key, val)
                to_update.append(agent)
                updated_count += 1
            else:
                to_create.append(AIAgent(slug=slug, **agent_data))
                created_count += 1

        if to_create:
            AIAgent.objects.bulk_create(to_create, batch_size=200)
        if to_update:
            update_fields = [
                "external_id",
                "name",
                "category",
                "category_name",
                "industry",
                "access",
                "pricing_model",
                "short_description",
                "long_description",
                "key_features",
                "use_cases",
                "logo_url",
                "image_url",
                "video_url",
                "popularity_score",
                "upvotes",
                "views",
                "bookmark_count",
                "review_count",
                "average_rating",
                "views_24h",
                "views_7d",
                "views_30d",
                "upvotes_24h",
                "upvotes_7d",
                "upvotes_30d",
                "website",
                "github_url",
                "twitter_url",
                "linkedin_url",
                "discord_url",
                "email",
                "is_featured",
                "seo_boost",
                "created_at",
            ]
            AIAgent.objects.bulk_update(to_update, update_fields, batch_size=200)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created_count} agents, "
                f"updated {updated_count} agents, "
                f"skipped {skipped_count} agents"
            )
        )

    def update_category_counts(self):
        self.stdout.write("Updating category agent counts...")

        categories = AgentCategory.objects.all()
        to_update = []
        for cat in categories:
            actual_count = cat.agents.count()
            if cat.agent_count != actual_count:
                cat.agent_count = actual_count
                to_update.append(cat)

        if to_update:
            AgentCategory.objects.bulk_update(
                to_update, ["agent_count"], batch_size=200
            )

        self.stdout.write(
            self.style.SUCCESS(f"Updated agent counts for {len(to_update)} categories")
        )
