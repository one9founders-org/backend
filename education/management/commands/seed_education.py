from django.core.management.base import BaseCommand

from education.models import (
    AudienceType,
    Course,
    CourseCategory,
    CourseModule,
    EducationGuide,
    Instructor,
    LandingPage,
)


class Command(BaseCommand):
    help = "Seed education app with initial data"

    def handle(self, *args, **options):
        self.stdout.write("Seeding education data...")

        # ── Audiences ──────────────────────────────────────────────────
        audiences_data = [
            {
                "name": "Students",
                "slug": "students",
                "description": "College students and recent graduates looking to build practical AI skills.",
                "icon": "graduation-cap",
                "landing_page_url": "/education/students",
                "order": 1,
            },
            {
                "name": "Working Professionals",
                "slug": "working-professionals",
                "description": "Professionals looking to upskill in AI tools for their industry.",
                "icon": "briefcase",
                "landing_page_url": "/education/professionals",
                "order": 2,
            },
            {
                "name": "Entrepreneurs",
                "slug": "entrepreneurs",
                "description": "Founders and business owners looking to leverage AI for growth.",
                "icon": "rocket",
                "landing_page_url": "/education/entrepreneurs",
                "order": 3,
            },
            {
                "name": "SME Owners",
                "slug": "sme-owners",
                "description": "Small and medium enterprise owners looking to adopt AI in operations.",
                "icon": "building",
                "landing_page_url": "/education/organizations",
                "order": 4,
            },
        ]
        audiences = {}
        for data in audiences_data:
            obj, created = AudienceType.objects.update_or_create(
                slug=data["slug"], defaults=data
            )
            audiences[data["slug"]] = obj
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} audience: {obj.name}")

        # ── Categories ─────────────────────────────────────────────────
        categories_data = [
            {
                "name": "AI Fundamentals",
                "slug": "ai-fundamentals",
                "description": "Core AI concepts, prompt engineering, and foundational tools.",
                "icon": "brain",
                "order": 1,
            },
            {
                "name": "Content & Marketing",
                "slug": "content-marketing",
                "description": "AI-powered content creation, marketing automation, and brand building.",
                "icon": "megaphone",
                "order": 2,
            },
            {
                "name": "Coding & Dev",
                "slug": "coding-dev",
                "description": "AI-assisted development, no-code tools, and automation.",
                "icon": "code",
                "order": 3,
            },
            {
                "name": "Automation",
                "slug": "automation",
                "description": "Workflow automation, integrations, and productivity tools.",
                "icon": "cog",
                "order": 4,
            },
            {
                "name": "Data & Analytics",
                "slug": "data-analytics",
                "description": "Data analysis, visualization, and AI-driven insights.",
                "icon": "chart-bar",
                "order": 5,
            },
            {
                "name": "Business & Strategy",
                "slug": "business-strategy",
                "description": "AI strategy, business models, and organizational transformation.",
                "icon": "lightbulb",
                "order": 6,
            },
        ]
        categories = {}
        for data in categories_data:
            obj, created = CourseCategory.objects.update_or_create(
                slug=data["slug"], defaults=data
            )
            categories[data["slug"]] = obj
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} category: {obj.name}")

        # ── Instructor (placeholder) ───────────────────────────────────
        instructor, created = Instructor.objects.update_or_create(
            slug="one9-team",
            defaults={
                "name": "One9 Founders Team",
                "title": "AI Education Experts",
                "bio": "The One9 Founders education team brings together AI practitioners and educators to deliver practical, industry-relevant training supported by IIT Bombay.",
                "short_bio": "AI Education Experts at One9 Founders",
                "is_active": True,
            },
        )
        self.stdout.write(
            f"  {'Created' if created else 'Updated'} instructor: {instructor.name}"
        )

        # ── Landing Pages ──────────────────────────────────────────────
        landing_pages_data = [
            {
                "page_type": "students",
                "hero_title": "Your College Won't Teach You This. We Will.",
                "hero_subtitle": "Practical AI skills for placements and your first job. Supported by IIT Bombay.",
                "hero_cta_text": "Explore Courses",
                "hero_cta_url": "/education/courses",
                "pitch_title": "Why Students Choose One9",
                "pitch_content": "Get ahead of your peers with practical AI skills that matter in today's job market. Our programs are designed in collaboration with IIT Bombay Educational Outreach to ensure you learn what the industry actually needs.",
            },
            {
                "page_type": "professionals",
                "hero_title": "AI Won't Replace You. Someone Using AI Will.",
                "hero_subtitle": "Upskill in AI tools transforming your industry.",
                "hero_cta_text": "Start Learning",
                "hero_cta_url": "/education/courses",
                "pitch_title": "Stay Relevant. Stay Ahead.",
                "pitch_content": "The professionals who thrive tomorrow are the ones learning AI today. Our courses are built for busy professionals who need practical, immediately applicable skills.",
            },
            {
                "page_type": "entrepreneurs",
                "hero_title": "Build Faster. Spend Less. Scale Smarter.",
                "hero_subtitle": "AI tools for founders. No technical co-founder required.",
                "hero_cta_text": "Explore Programs",
                "hero_cta_url": "/education/courses",
                "pitch_title": "AI-Powered Entrepreneurship",
                "pitch_content": "Every founder needs to understand AI — not to write code, but to build smarter businesses. Learn how to use AI to automate operations, create content, and scale faster.",
            },
            {
                "page_type": "organizations",
                "hero_title": "Bring AI Training to Your Campus or Organization",
                "hero_subtitle": "Custom programs for colleges and corporates. Supported by IIT Bombay.",
                "hero_cta_text": "Get in Touch",
                "hero_cta_url": "/education/contact",
                "pitch_title": "Enterprise & Campus Programs",
                "pitch_content": "We work with colleges, corporates, and organizations to design custom AI training programs. Our programs are backed by IIT Bombay Educational Outreach and tailored to your specific needs.",
            },
        ]
        for data in landing_pages_data:
            obj, created = LandingPage.objects.update_or_create(
                page_type=data["page_type"], defaults=data
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} landing page: {data['page_type']}")

        # ── Sample Courses (draft) ─────────────────────────────────────
        courses_data = [
            {
                "title": "AI Fundamentals: From Zero to Prompt Engineer",
                "slug": "ai-fundamentals-prompt-engineering",
                "subtitle": "Master the art of communicating with AI",
                "short_description": "Learn prompt engineering, ChatGPT, Claude, and other AI tools from scratch.",
                "description": "A comprehensive course covering AI fundamentals, prompt engineering techniques, and practical applications across ChatGPT, Claude, Gemini, and more.",
                "category": categories["ai-fundamentals"],
                "difficulty": "beginner",
                "format": "cohort",
                "status": "draft",
                "duration_weeks": 4,
                "hours_per_week": 5,
                "total_lessons": 16,
                "whats_included": [
                    "16 live sessions",
                    "Hands-on projects",
                    "Community access",
                    "Certificate from IIT Bombay EO",
                ],
                "tools_mentioned": ["chatgpt", "claude", "gemini", "midjourney"],
                "has_hindi_support": True,
            },
            {
                "title": "AI for Content Creators & Marketers",
                "slug": "ai-content-marketing",
                "subtitle": "Create better content 10x faster",
                "short_description": "Learn to use AI for writing, design, video, and marketing automation.",
                "description": "Master AI tools for content creation, social media marketing, SEO, and brand building. Designed for marketers, creators, and entrepreneurs.",
                "category": categories["content-marketing"],
                "difficulty": "beginner",
                "format": "self_paced",
                "status": "draft",
                "duration_weeks": 3,
                "hours_per_week": 4,
                "total_lessons": 12,
                "whats_included": [
                    "12 video lessons",
                    "Templates & prompts library",
                    "Community access",
                    "Certificate from IIT Bombay EO",
                ],
                "tools_mentioned": ["chatgpt", "canva", "midjourney", "jasper"],
                "has_hindi_support": False,
            },
            {
                "title": "No-Code AI App Building",
                "slug": "no-code-ai-app-building",
                "subtitle": "Build real apps without writing code",
                "short_description": "Learn to build AI-powered applications using no-code and low-code tools.",
                "description": "From idea to deployed app — learn to build AI-powered tools, chatbots, and automations using no-code platforms like Bubble, Make, and Zapier.",
                "category": categories["coding-dev"],
                "difficulty": "intermediate",
                "format": "cohort",
                "status": "draft",
                "duration_weeks": 6,
                "hours_per_week": 6,
                "total_lessons": 24,
                "whats_included": [
                    "24 live sessions",
                    "3 real-world projects",
                    "1-on-1 mentorship",
                    "Certificate from IIT Bombay EO",
                ],
                "tools_mentioned": ["bubble", "make", "zapier", "chatgpt-api"],
                "has_hindi_support": True,
            },
        ]
        for data in courses_data:
            course_audiences = []
            if data.get("difficulty") == "beginner":
                course_audiences = [
                    audiences["students"],
                    audiences["working-professionals"],
                ]
            else:
                course_audiences = [
                    audiences["working-professionals"],
                    audiences["entrepreneurs"],
                ]

            course, created = Course.objects.update_or_create(
                slug=data["slug"],
                defaults={k: v for k, v in data.items()},
            )
            course.instructors.add(instructor)
            course.audiences.set(course_audiences)
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} course: {course.title}")

            # Add sample modules
            if created:
                for i in range(1, 4):
                    CourseModule.objects.create(
                        course=course,
                        title=f"Module {i}: {['Foundation', 'Application', 'Mastery'][i-1]}",
                        description=f"Module {i} content for {course.title}",
                        order=i,
                        duration_description=f"Week {i}",
                    )

        # ── Sample Guides (draft) ──────────────────────────────────────
        guides_data = [
            {
                "title": "The Complete Guide to ChatGPT for Business",
                "slug": "chatgpt-for-business-guide",
                "subtitle": "Everything you need to know about using ChatGPT in your business",
                "excerpt": "A comprehensive guide covering ChatGPT use cases, prompt techniques, and implementation strategies for businesses of all sizes.",
                "content": "# ChatGPT for Business\n\nThis guide covers everything from basic prompt engineering to advanced business applications of ChatGPT.\n\n## What You'll Learn\n- Effective prompt engineering\n- Business use cases\n- Integration strategies\n- ROI measurement",
                "category": categories["ai-fundamentals"],
                "author": instructor,
                "difficulty": "beginner",
                "status": "draft",
                "read_time_minutes": 15,
                "tools_mentioned": ["chatgpt", "chatgpt-api"],
            },
            {
                "title": "AI Automation Playbook for Small Businesses",
                "slug": "ai-automation-playbook-smb",
                "subtitle": "Automate your business operations with AI",
                "excerpt": "Step-by-step playbook for implementing AI automation in small and medium businesses.",
                "content": "# AI Automation Playbook\n\nLearn how to identify automation opportunities, choose the right tools, and implement AI-powered workflows.\n\n## Key Areas\n- Customer support automation\n- Marketing automation\n- Operations optimization\n- Financial process automation",
                "category": categories["automation"],
                "author": instructor,
                "difficulty": "intermediate",
                "status": "draft",
                "read_time_minutes": 20,
                "tools_mentioned": ["make", "zapier", "chatgpt", "notion-ai"],
            },
        ]
        for data in guides_data:
            guide, created = EducationGuide.objects.update_or_create(
                slug=data["slug"],
                defaults=data,
            )
            guide.audiences.set(
                [audiences["working-professionals"], audiences["entrepreneurs"]]
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} guide: {guide.title}")

        self.stdout.write(
            self.style.SUCCESS("\nEducation seed data loaded successfully!")
        )
