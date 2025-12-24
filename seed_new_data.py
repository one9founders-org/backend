import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from datetime import datetime

from api.models import Category, Tool

# Create categories
categories_data = [
    {
        "name": "AI & Machine Learning",
        "slug": "ai-ml",
        "description": "AI-powered tools and ML platforms",
    },
    {
        "name": "Productivity",
        "slug": "productivity",
        "description": "Tools to boost productivity",
    },
    {"name": "Design", "slug": "design", "description": "Design and creative tools"},
    {
        "name": "Development",
        "slug": "development",
        "description": "Developer tools and platforms",
    },
    {
        "name": "Marketing",
        "slug": "marketing",
        "description": "Marketing and analytics tools",
    },
]

print("Creating categories...")
for cat_data in categories_data:
    cat, created = Category.objects.get_or_create(
        slug=cat_data["slug"], defaults=cat_data
    )
    print(f"  {'Created' if created else 'Exists'}: {cat.name}")

# Create tools
tools_data = [
    {
        "name": "ChatGPT",
        "slug": "chatgpt",
        "short_description": "AI-powered conversational assistant",
        "description": "ChatGPT is an advanced AI language model that can help with content creation, coding, problem-solving, and more.",
        "website": "https://chat.openai.com",
        "logo_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=300&h=200&fit=crop",
        "pricing_models": ["free", "paid"],
        "pricing_from": 20,
        "free_tier_available": True,
        "tags": ["AI", "chatbot", "content creation"],
        "use_cases": ["content writing", "code generation", "customer support"],
        "features": [
            "Natural language processing",
            "Code generation",
            "Multi-language support",
        ],
        "platforms": ["web", "mobile"],
        "startup_friendly": True,
        "startup_benefits": "Free tier available for startups to get started",
        "ideal_for": ["early-stage", "bootstrapped", "SaaS"],
        "rating": 4.8,
        "review_count": 2847,
        "verified": True,
        "is_featured": True,
        "categories": ["ai-ml", "productivity"],
    },
    {
        "name": "Midjourney",
        "slug": "midjourney",
        "short_description": "AI image generation platform",
        "description": "Midjourney is an AI-powered image generation tool that creates stunning visual content from text descriptions.",
        "website": "https://midjourney.com",
        "logo_url": "https://images.unsplash.com/photo-1547036967-23d11aacaee0?w=300&h=200&fit=crop",
        "pricing_models": ["paid"],
        "pricing_from": 10,
        "free_tier_available": False,
        "free_trial_days": 7,
        "tags": ["AI", "image generation", "design"],
        "use_cases": ["marketing visuals", "social media content", "concept art"],
        "features": ["Text-to-image", "High resolution", "Style variations"],
        "platforms": ["discord", "web"],
        "startup_friendly": True,
        "startup_benefits": "7-day free trial for new users",
        "ideal_for": ["design-focused", "marketing"],
        "rating": 4.7,
        "review_count": 1923,
        "verified": True,
        "is_featured": True,
        "categories": ["ai-ml", "design"],
    },
    {
        "name": "Notion",
        "slug": "notion",
        "short_description": "All-in-one workspace",
        "description": "Notion is a versatile workspace that combines notes, tasks, wikis, and databases in one place.",
        "website": "https://notion.so",
        "logo_url": "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=300&h=200&fit=crop",
        "pricing_models": ["free", "freemium", "paid"],
        "pricing_from": 8,
        "free_tier_available": True,
        "tags": ["productivity", "collaboration", "notes"],
        "use_cases": ["project management", "documentation", "knowledge base"],
        "features": ["Databases", "Templates", "Collaboration", "API"],
        "platforms": ["web", "desktop", "mobile"],
        "startup_friendly": True,
        "startup_benefits": "Free for small teams, generous free tier",
        "ideal_for": ["early-stage", "remote teams"],
        "rating": 4.6,
        "review_count": 3421,
        "verified": True,
        "is_featured": False,
        "categories": ["productivity"],
    },
    {
        "name": "Figma",
        "slug": "figma",
        "short_description": "Collaborative design platform",
        "description": "Figma is a cloud-based design tool for creating user interfaces, prototypes, and design systems.",
        "website": "https://figma.com",
        "logo_url": "https://images.unsplash.com/photo-1561070791-2526d30994b5?w=300&h=200&fit=crop",
        "pricing_models": ["free", "paid"],
        "pricing_from": 12,
        "free_tier_available": True,
        "tags": ["design", "UI/UX", "collaboration"],
        "use_cases": ["UI design", "prototyping", "design systems"],
        "features": [
            "Real-time collaboration",
            "Prototyping",
            "Design systems",
            "Plugins",
        ],
        "platforms": ["web", "desktop"],
        "startup_friendly": True,
        "startup_benefits": "Free for up to 3 projects",
        "ideal_for": ["design-focused", "product teams"],
        "rating": 4.9,
        "review_count": 5234,
        "verified": True,
        "is_featured": True,
        "categories": ["design"],
    },
]

print("\nCreating tools...")
for tool_data in tools_data:
    category_slugs = tool_data.pop("categories", [])
    tool, created = Tool.objects.get_or_create(
        slug=tool_data["slug"], defaults=tool_data
    )

    # Add categories
    for cat_slug in category_slugs:
        try:
            category = Category.objects.get(slug=cat_slug)
            tool.categories.add(category)
        except Category.DoesNotExist:
            pass

    print(f"  {'Created' if created else 'Exists'}: {tool.name}")

print("\n✅ Seed data created successfully!")
print(f"   Categories: {Category.objects.count()}")
print(f"   Tools: {Tool.objects.count()}")
