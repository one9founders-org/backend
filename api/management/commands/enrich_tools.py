import json
import os
import sys
import time

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from api.models import Category, Tool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


AI_TOOL_CATEGORIES = [
    (
        "writing",
        "Writing",
        "AI tools for content creation, copywriting, and text generation",
    ),
    ("images", "Images", "AI image generation, editing, and enhancement tools"),
    ("video", "Video", "AI video creation, editing, and enhancement tools"),
    ("audio", "Audio", "AI audio processing, generation, and editing tools"),
    ("music", "Music", "AI music composition and generation tools"),
    ("code", "Code", "AI coding assistants and developer tools"),
    ("chatbots", "Chatbots", "AI chatbots and conversational agents"),
    ("customer-support", "Customer Support", "AI customer service and support tools"),
    ("marketing", "Marketing", "AI marketing automation and analytics tools"),
    ("seo", "SEO", "AI search engine optimization tools"),
    ("social-media", "Social Media", "AI social media management and content tools"),
    ("email", "Email", "AI email writing and automation tools"),
    ("sales", "Sales", "AI sales automation and CRM tools"),
    ("productivity", "Productivity", "AI productivity and workflow tools"),
    ("research", "Research", "AI research and analysis tools"),
    ("education", "Education", "AI learning and education tools"),
    ("finance", "Finance", "AI financial analysis and management tools"),
    ("legal", "Legal", "AI legal document and contract tools"),
    ("hr", "HR", "AI human resources and recruiting tools"),
    ("design", "Design", "AI design and creative tools"),
    ("3d", "3D", "AI 3D modeling and rendering tools"),
    ("voice", "Voice", "AI voice synthesis and cloning tools"),
    ("transcription", "Transcription", "AI speech-to-text and transcription tools"),
    ("translation", "Translation", "AI translation and localization tools"),
    ("data-analysis", "Data Analysis", "AI data analytics and visualization tools"),
    ("automation", "Automation", "AI workflow automation tools"),
    ("no-code", "No-Code", "AI no-code and low-code development tools"),
    ("developer-tools", "Developer Tools", "AI tools for software development"),
    ("security", "Security", "AI cybersecurity and privacy tools"),
    ("healthcare", "Healthcare", "AI healthcare and medical tools"),
    ("real-estate", "Real Estate", "AI real estate and property tools"),
    ("ecommerce", "E-commerce", "AI e-commerce and retail tools"),
    ("personal-assistant", "Personal Assistant", "AI personal assistant tools"),
    ("meeting", "Meeting", "AI meeting and collaboration tools"),
    ("presentation", "Presentation", "AI presentation creation tools"),
    ("documents", "Documents", "AI document processing and management tools"),
    ("search", "Search", "AI search and discovery tools"),
    ("analytics", "Analytics", "AI business analytics and insights tools"),
    (
        "startup-tools",
        "Startup Tools",
        "AI tools specifically for startups and founders",
    ),
]


def get_openai_client():
    """Get OpenAI client (v1.0.0+ API)."""
    try:
        from django.conf import settings
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return client
    except Exception as e:
        print(f"Error initializing OpenAI: {e}")
        return None


def determine_pricing_type_from_data(tool):
    """
    Determine pricing_type based on existing tool data.
    """
    pricing_models = tool.pricing_models or []
    free_tier = tool.free_tier_available
    pricing_from = tool.pricing_from

    if "free" in pricing_models and len(pricing_models) == 1:
        return "free"
    elif free_tier or ("free" in pricing_models and len(pricing_models) > 1):
        return "freemium"
    elif pricing_from and float(pricing_from) > 0:
        return "paid"
    elif "paid" in pricing_models or "subscription" in pricing_models:
        return "paid"

    return None


def determine_categories_with_ai(openai_client, tool):
    """
    Use AI to determine appropriate categories for a tool.
    """
    if not openai_client:
        return []

    category_names = [cat[1] for cat in AI_TOOL_CATEGORIES]

    prompt = f"""Given this AI tool, select the most relevant categories (1-3 categories max).

Tool Name: {tool.name}
Description: {tool.description[:500] if tool.description else 'N/A'}
Short Description: {tool.short_description or 'N/A'}
Tags: {', '.join(tool.tags or [])}
Use Cases: {', '.join(tool.use_cases or [])}

Available Categories: {', '.join(category_names)}

Return ONLY a JSON array of category names that best match this tool.
Example: ["Writing", "Marketing", "SEO"]

JSON array:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        result = response.choices[0].message.content.strip()
        result = result.replace("```json", "").replace("```", "").strip()
        categories = json.loads(result)
        return [c for c in categories if c in category_names]
    except Exception as e:
        print(f"Error determining categories for {tool.name}: {e}")
        return []


def determine_pricing_with_ai(openai_client, tool):
    """
    Use AI to determine pricing_type based on tool description and data.
    """
    if not openai_client:
        return None

    prompt = f"""Determine the pricing type for this AI tool based on the information provided.

Tool Name: {tool.name}
Description: {tool.description[:500] if tool.description else 'N/A'}
Pricing Models: {tool.pricing_models or 'Unknown'}
Free Tier Available: {tool.free_tier_available}
Pricing From: ${tool.pricing_from or 'Unknown'}

Pricing types:
- "free": Completely free to use, no paid plans
- "freemium": Has a free tier/plan but also paid options
- "paid": Requires payment to use, no free tier

Return ONLY one word: free, freemium, or paid"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().lower()
        if result in ["free", "freemium", "paid"]:
            return result
    except Exception as e:
        print(f"Error determining pricing for {tool.name}: {e}")

    return None


class Command(BaseCommand):
    help = "Enrich tools with categories and pricing_type using AI and TAAFT data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tool-id",
            type=int,
            help="Enrich a specific tool by ID",
        )
        parser.add_argument(
            "--tool-name",
            type=str,
            help="Enrich a specific tool by name",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Enrich all tools",
        )
        parser.add_argument(
            "--create-categories",
            action="store_true",
            help="Create default AI tool categories",
        )
        parser.add_argument(
            "--use-taaft",
            action="store_true",
            help="Use TAAFT scraper for pricing info (slower)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of tools to process",
        )

    def handle(self, *args, **options):
        if options["create_categories"]:
            self.create_categories()
            return

        openai_client = get_openai_client()
        if not openai_client:
            self.stdout.write(
                self.style.WARNING("OpenAI not configured. Using rule-based approach.")
            )

        tools = self.get_tools(options)
        if not tools:
            self.stdout.write(self.style.WARNING("No tools found to process."))
            return

        self.stdout.write(f"Processing {len(tools)} tools...")

        taaft_driver = None
        if options["use_taaft"]:
            try:
                from scrapers.taaft import create_driver

                taaft_driver = create_driver()
                self.stdout.write("TAAFT scraper initialized.")
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Could not initialize TAAFT scraper: {e}")
                )

        updated_count = 0
        for i, tool in enumerate(tools):
            self.stdout.write(f"\n[{i + 1}/{len(tools)}] Processing: {tool.name}")

            changes = {}

            if tool.pricing_type == "freemium":
                pricing_type = determine_pricing_type_from_data(tool)

                if not pricing_type and options["use_taaft"] and taaft_driver:
                    try:
                        from scrapers.taaft import search_tool_pricing

                        result = search_tool_pricing(tool.name, taaft_driver)
                        if result.get("found") and result.get("pricing_type"):
                            pricing_type = result["pricing_type"]
                            self.stdout.write(
                                f"  TAAFT pricing: {result.get('pricing_text')}"
                            )
                    except Exception as e:
                        self.stdout.write(f"  TAAFT error: {e}")

                if not pricing_type and openai_client:
                    pricing_type = determine_pricing_with_ai(openai_client, tool)

                if pricing_type and pricing_type != tool.pricing_type:
                    changes["pricing_type"] = pricing_type

            if not tool.categories.exists():
                if openai_client:
                    category_names = determine_categories_with_ai(openai_client, tool)
                    if category_names:
                        changes["categories"] = category_names

            if changes:
                self.stdout.write(f"  Changes: {changes}")

                if not options["dry_run"]:
                    if "pricing_type" in changes:
                        tool.pricing_type = changes["pricing_type"]
                        tool.save(update_fields=["pricing_type"])

                    if "categories" in changes:
                        for cat_name in changes["categories"]:
                            slug = slugify(cat_name)
                            try:
                                category = Category.objects.get(slug=slug)
                            except Category.DoesNotExist:
                                try:
                                    category = Category.objects.get(name=cat_name)
                                except Category.DoesNotExist:
                                    category = Category.objects.create(
                                        slug=slug,
                                        name=cat_name,
                                    )
                            tool.categories.add(category)

                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  Updated {tool.name}"))
            else:
                self.stdout.write("  No changes needed.")

            if options["use_taaft"]:
                time.sleep(1)

        if taaft_driver:
            taaft_driver.quit()

        self.stdout.write(self.style.SUCCESS(f"\nDone! Updated {updated_count} tools."))

    def get_tools(self, options):
        """Get tools to process based on options."""
        if options["tool_id"]:
            return Tool.objects.filter(id=options["tool_id"])
        elif options["tool_name"]:
            return Tool.objects.filter(name__icontains=options["tool_name"])
        elif options["all"]:
            queryset = Tool.objects.all()
            if options["limit"]:
                queryset = queryset[: options["limit"]]
            return queryset
        else:
            self.stdout.write(
                self.style.ERROR("Please specify --tool-id, --tool-name, or --all")
            )
            return None

    def create_categories(self):
        """Create default AI tool categories."""
        created_count = 0
        for slug, name, description in AI_TOOL_CATEGORIES:
            category, created = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"Created category: {name}")
            else:
                self.stdout.write(f"Category exists: {name}")

        self.stdout.write(
            self.style.SUCCESS(f"\nCreated {created_count} new categories.")
        )
