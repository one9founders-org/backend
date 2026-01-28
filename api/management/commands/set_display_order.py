from django.core.management.base import BaseCommand

from api.models import Category, Tool

TOP_100_TOOLS = [
    "ChatGPT",
    "Midjourney",
    "Notion AI",
    "GitHub Copilot",
    "Canva AI",
    "Claude",
    "ElevenLabs",
    "Jasper",
    "Runway",
    "Grammarly",
    "Perplexity",
    "HeyGen",
    "Copy.ai",
    "Cursor",
    "Otter.ai",
    "DALL-E 3",
    "Zapier AI",
    "Surfer SEO",
    "Descript",
    "Gemini",
    "Fireflies.ai",
    "Leonardo.ai",
    "Writesonic",
    "Motion",
    "Synthesia",
    "Figma AI",
    "Stable Diffusion",
    "Murf.ai",
    "Rytr",
    "Pika Labs",
    "Tabnine",
    "QuillBot",
    "Reclaim.ai",
    "Ideogram",
    "Pictory",
    "Wordtune",
    "Adobe Firefly",
    "Gong",
    "InVideo AI",
    "Codeium",
    "MarketMuse",
    "Beautiful.ai",
    "Playground AI",
    "Speechify",
    "Mem",
    "Opus Clip",
    "Looka",
    "Phind",
    "Play.ht",
    "Drift",
    "Adcreative.ai",
    "DreamStudio",
    "Replit AI",
    "Frase",
    "Kapwing AI",
    "Intercom Fin",
    "LOVO",
    "Uizard",
    "Anyword",
    "Fliki",
    "Make (Integromat)",
    "Lexica",
    "Resemble AI",
    "ClickUp AI",
    "Microsoft Copilot",
    "Khroma",
    "Chorus.ai",
    "Listnr",
    "Zendesk AI",
    "Designs.ai",
    "CodeWhisperer",
    "Lately",
    "Booth.ai",
    "Bardeen",
    "Semrush AI",
    "Ada",
    "Audyo",
    "Flair AI",
    "Sourcegraph Cody",
    "People.ai",
    "Krisp",
    "Remove.bg",
    "Meta AI",
    "Todoist AI",
    "Seventh Sense",
    "AI2sql",
    "Character.AI",
    "Cleanup.pictures",
    "Adobe Podcast AI",
    "Exceed.ai",
    "Phrasee",
    "Pieces",
    "Pi",
    "Conversica",
    "Albert AI",
    "Pencil",
    "Poe",
    "Simplified",
    "LivePerson",
    "Julius",
]

TOOL_CATEGORIES = {
    "ChatGPT": ["Productivity", "Writing"],
    "Midjourney": ["Image Generation", "Design"],
    "Notion AI": ["Productivity", "Writing"],
    "GitHub Copilot": ["Developer Tools", "Code"],
    "Canva AI": ["Design", "Image Generation"],
    "Claude": ["Productivity", "Writing"],
    "ElevenLabs": ["Audio", "Voice"],
    "Jasper": ["Writing", "Marketing"],
    "Runway": ["Video", "Image Generation"],
    "Grammarly": ["Writing", "Productivity"],
    "Perplexity": ["Research", "Productivity"],
    "HeyGen": ["Video", "Marketing"],
    "Copy.ai": ["Writing", "Marketing"],
    "Cursor": ["Developer Tools", "Code"],
    "Otter.ai": ["Audio", "Productivity"],
    "DALL-E 3": ["Image Generation", "Design"],
    "Zapier AI": ["Automation", "Productivity"],
    "Surfer SEO": ["SEO", "Marketing"],
    "Descript": ["Video", "Audio"],
    "Gemini": ["Productivity", "Writing"],
    "Fireflies.ai": ["Audio", "Productivity"],
    "Leonardo.ai": ["Image Generation", "Design"],
    "Writesonic": ["Writing", "Marketing"],
    "Motion": ["Productivity", "Project Management"],
    "Synthesia": ["Video", "Marketing"],
    "Figma AI": ["Design", "Productivity"],
    "Stable Diffusion": ["Image Generation", "Design"],
    "Murf.ai": ["Audio", "Voice"],
    "Rytr": ["Writing", "Marketing"],
    "Pika Labs": ["Video", "Image Generation"],
    "Tabnine": ["Developer Tools", "Code"],
    "QuillBot": ["Writing", "Productivity"],
    "Reclaim.ai": ["Productivity", "Calendar"],
    "Ideogram": ["Image Generation", "Design"],
    "Pictory": ["Video", "Marketing"],
    "Wordtune": ["Writing", "Productivity"],
    "Adobe Firefly": ["Image Generation", "Design"],
    "Gong": ["Sales", "Analytics"],
    "InVideo AI": ["Video", "Marketing"],
    "Codeium": ["Developer Tools", "Code"],
    "MarketMuse": ["SEO", "Content"],
    "Beautiful.ai": ["Presentation", "Design"],
    "Playground AI": ["Image Generation", "Design"],
    "Speechify": ["Audio", "Productivity"],
    "Mem": ["Productivity", "Notes"],
    "Opus Clip": ["Video", "Social Media"],
    "Looka": ["Design", "Branding"],
    "Phind": ["Developer Tools", "Research"],
    "Play.ht": ["Audio", "Voice"],
    "Drift": ["Sales", "Customer Support"],
    "Adcreative.ai": ["Marketing", "Design"],
    "DreamStudio": ["Image Generation", "Design"],
    "Replit AI": ["Developer Tools", "Code"],
    "Frase": ["SEO", "Writing"],
    "Kapwing AI": ["Video", "Design"],
    "Intercom Fin": ["Customer Support", "Sales"],
    "LOVO": ["Audio", "Voice"],
    "Uizard": ["Design", "Prototyping"],
    "Anyword": ["Writing", "Marketing"],
    "Fliki": ["Video", "Audio"],
    "Make (Integromat)": ["Automation", "Productivity"],
    "Lexica": ["Image Generation", "Research"],
    "Resemble AI": ["Audio", "Voice"],
    "ClickUp AI": ["Productivity", "Project Management"],
    "Microsoft Copilot": ["Productivity", "Writing"],
    "Khroma": ["Design", "Color"],
    "Chorus.ai": ["Sales", "Analytics"],
    "Listnr": ["Audio", "Voice"],
    "Zendesk AI": ["Customer Support", "Sales"],
    "Designs.ai": ["Design", "Marketing"],
    "CodeWhisperer": ["Developer Tools", "Code"],
    "Lately": ["Social Media", "Marketing"],
    "Booth.ai": ["Image Generation", "E-commerce"],
    "Bardeen": ["Automation", "Productivity"],
    "Semrush AI": ["SEO", "Marketing"],
    "Ada": ["Customer Support", "Chatbot"],
    "Audyo": ["Audio", "Voice"],
    "Flair AI": ["Image Generation", "E-commerce"],
    "Sourcegraph Cody": ["Developer Tools", "Code"],
    "People.ai": ["Sales", "Analytics"],
    "Krisp": ["Audio", "Productivity"],
    "Remove.bg": ["Image Generation", "Design"],
    "Meta AI": ["Productivity", "Writing"],
    "Todoist AI": ["Productivity", "Task Management"],
    "Seventh Sense": ["Marketing", "Email"],
    "AI2sql": ["Developer Tools", "Database"],
    "Character.AI": ["Entertainment", "Chatbot"],
    "Cleanup.pictures": ["Image Generation", "Design"],
    "Adobe Podcast AI": ["Audio", "Podcast"],
    "Exceed.ai": ["Sales", "Marketing"],
    "Phrasee": ["Marketing", "Email"],
    "Pieces": ["Developer Tools", "Productivity"],
    "Pi": ["Productivity", "Chatbot"],
    "Conversica": ["Sales", "Marketing"],
    "Albert AI": ["Marketing", "Advertising"],
    "Pencil": ["Marketing", "Design"],
    "Poe": ["Productivity", "Chatbot"],
    "Simplified": ["Design", "Marketing"],
    "LivePerson": ["Customer Support", "Sales"],
    "Julius": ["Analytics", "Data"],
}


class Command(BaseCommand):
    help = "Set display_order for tools based on the Top 100 list"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without making changes",
        )
        parser.add_argument(
            "--assign-categories",
            action="store_true",
            help="Also assign categories to tools if not already assigned",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        assign_categories = options["assign_categories"]

        self.stdout.write("Setting display_order for Top 100 tools...")

        updated_count = 0
        not_found = []
        category_updates = 0

        for index, tool_name in enumerate(TOP_100_TOOLS, start=1):
            tool = Tool.objects.filter(name__iexact=tool_name).first()
            if not tool:
                tool = Tool.objects.filter(name__icontains=tool_name).first()

            if tool:
                if dry_run:
                    self.stdout.write(
                        f"  Would set {tool.name} display_order to {index}"
                    )
                else:
                    tool.display_order = index
                    tool.save(update_fields=["display_order"])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Set {tool.name} display_order to {index}"
                        )
                    )
                updated_count += 1

                if assign_categories and tool_name in TOOL_CATEGORIES:
                    category_names = TOOL_CATEGORIES[tool_name]
                    for cat_name in category_names:
                        category = Category.objects.filter(
                            name__iexact=cat_name
                        ).first()
                        if category and category not in tool.categories.all():
                            if dry_run:
                                msg = f"    Would add category '{cat_name}'"
                                self.stdout.write(f"{msg} to {tool.name}")
                            else:
                                tool.categories.add(category)
                                self.stdout.write(
                                    f"    Added category '{cat_name}' to {tool.name}"
                                )
                            category_updates += 1
            else:
                not_found.append(tool_name)

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Updated {updated_count} tools"))

        if assign_categories:
            self.stdout.write(
                self.style.SUCCESS(f"Category assignments: {category_updates}")
            )

        if not_found:
            self.stdout.write(
                self.style.WARNING(f"\nTools not found ({len(not_found)}):")
            )
            for name in not_found:
                self.stdout.write(f"  - {name}")
