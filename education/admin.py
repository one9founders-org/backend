from django.contrib import admin

from .models import (
    AudienceType,
    Course,
    CourseCategory,
    CourseFAQ,
    CourseInquiry,
    CourseModule,
    EducationGuide,
    EducationWorkshop,
    Instructor,
    LandingPage,
    LearningPath,
    LearningPathModule,
    OrganizationInquiry,
    WorkshopRegistration,
)

# ── Inlines ────────────────────────────────────────────────────────────


class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 1
    fields = ["title", "description", "order", "duration_description"]


class CourseFAQInline(admin.TabularInline):
    model = CourseFAQ
    extra = 1
    fields = ["question", "answer", "order"]


class LearningPathModuleInline(admin.StackedInline):
    model = LearningPathModule
    extra = 1
    filter_horizontal = ["courses", "guides", "workshops"]


# ── Lookup / Taxonomy ──────────────────────────────────────────────────


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order", "is_active"]
    list_editable = ["order", "is_active"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(AudienceType)
class AudienceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "order", "is_active"]
    list_editable = ["order", "is_active"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ["name", "title", "is_active"]
    list_filter = ["is_active"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "title", "bio"]
    readonly_fields = ["created_at", "updated_at"]


# ── Course ─────────────────────────────────────────────────────────────


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = [CourseModuleInline, CourseFAQInline]
    list_display = [
        "title",
        "category",
        "status",
        "difficulty",
        "format",
        "is_featured",
        "interest_count",
        "created_at",
    ]
    list_filter = ["status", "difficulty", "format", "category"]
    list_editable = ["status", "is_featured"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description", "short_description"]
    filter_horizontal = ["audiences", "instructors"]
    readonly_fields = ["interest_count", "rating", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic",
            {
                "fields": (
                    "title",
                    "slug",
                    "subtitle",
                    "short_description",
                    "description",
                    "featured_image",
                    "intro_video_url",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "category",
                    "audiences",
                    "instructors",
                    "difficulty",
                    "format",
                    "status",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "duration_weeks",
                    "hours_per_week",
                    "total_lessons",
                    "next_cohort_date",
                    "schedule_description",
                )
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "whats_included",
                    "tools_mentioned",
                    "language",
                    "has_hindi_support",
                )
            },
        ),
        (
            "Certificate",
            {"fields": ("has_certificate", "certificate_description")},
        ),
        (
            "External Links",
            {
                "fields": ("iitb_eo_link",),
                "classes": ("collapse",),
            },
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
        (
            "Tracking",
            {
                "fields": (
                    "is_featured",
                    "interest_count",
                    "rating",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# ── Guide ──────────────────────────────────────────────────────────────


@admin.register(EducationGuide)
class EducationGuideAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "category",
        "difficulty",
        "status",
        "is_featured",
        "view_count",
        "published_at",
    ]
    list_filter = ["status", "difficulty", "category"]
    list_editable = ["status", "is_featured"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "content", "excerpt"]
    filter_horizontal = ["audiences"]
    readonly_fields = ["view_count", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic",
            {
                "fields": (
                    "title",
                    "slug",
                    "subtitle",
                    "excerpt",
                    "content",
                    "featured_image",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "category",
                    "author",
                    "audiences",
                    "difficulty",
                    "status",
                    "read_time_minutes",
                    "tools_mentioned",
                )
            },
        ),
        (
            "Related",
            {
                "fields": ("related_course",),
                "classes": ("collapse",),
            },
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
        (
            "Tracking",
            {
                "fields": (
                    "is_featured",
                    "view_count",
                    "published_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# ── Workshop ───────────────────────────────────────────────────────────


@admin.register(EducationWorkshop)
class EducationWorkshopAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "date",
        "format",
        "status",
        "instructor",
        "registration_count",
        "is_featured",
    ]
    list_filter = ["status", "format", "category"]
    list_editable = ["status", "is_featured"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    filter_horizontal = ["audiences"]
    readonly_fields = ["registration_count", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic",
            {
                "fields": (
                    "title",
                    "slug",
                    "short_description",
                    "description",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "date",
                    "duration_minutes",
                    "timezone",
                    "platform",
                    "meeting_link",
                    "recording_url",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "format",
                    "status",
                    "category",
                    "instructor",
                    "audiences",
                )
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "max_participants",
                    "learning_outcomes",
                    "prerequisites",
                )
            },
        ),
        (
            "Tracking",
            {
                "fields": (
                    "registration_count",
                    "is_featured",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# ── Learning Path ──────────────────────────────────────────────────────


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    inlines = [LearningPathModuleInline]
    list_display = ["title", "audience", "order", "is_active"]
    list_editable = ["order", "is_active"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "description"]
    readonly_fields = ["created_at", "updated_at"]


# ── Landing Page ───────────────────────────────────────────────────────


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ["page_type", "hero_title", "is_active"]
    list_filter = ["is_active", "page_type"]
    filter_horizontal = ["featured_courses"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            "Hero",
            {
                "fields": (
                    "page_type",
                    "hero_title",
                    "hero_subtitle",
                    "hero_cta_text",
                    "hero_cta_url",
                    "hero_image",
                )
            },
        ),
        (
            "Pitch",
            {"fields": ("pitch_title", "pitch_content")},
        ),
        (
            "Content",
            {"fields": ("content_blocks", "featured_courses")},
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
        (
            "Status",
            {"fields": ("is_active", "created_at", "updated_at")},
        ),
    )


# ── CRM: CourseInquiry ─────────────────────────────────────────────────


@admin.register(CourseInquiry)
class CourseInquiryAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "email",
        "course",
        "status",
        "follow_up_date",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    list_editable = ["status", "follow_up_date"]
    search_fields = ["name", "email", "phone", "city", "message"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            "Contact",
            {
                "fields": (
                    "name",
                    "email",
                    "phone",
                    "city",
                    "current_role",
                )
            },
        ),
        (
            "Interest",
            {
                "fields": (
                    "course",
                    "workshop",
                    "learning_path",
                    "source_page",
                    "message",
                )
            },
        ),
        (
            "Pipeline",
            {"fields": ("status", "internal_notes", "follow_up_date")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )


# ── CRM: OrganizationInquiry ──────────────────────────────────────────


@admin.register(OrganizationInquiry)
class OrganizationInquiryAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "name",
        "email",
        "inquiry_type",
        "status",
        "estimated_batch_size",
        "follow_up_date",
        "created_at",
    ]
    list_filter = ["inquiry_type", "status", "created_at"]
    list_editable = ["status", "follow_up_date"]
    search_fields = [
        "name",
        "email",
        "organization",
        "phone",
        "city",
        "message",
    ]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            "Contact",
            {
                "fields": (
                    "name",
                    "email",
                    "phone",
                    "organization",
                    "role",
                    "city",
                )
            },
        ),
        (
            "Details",
            {
                "fields": (
                    "inquiry_type",
                    "estimated_batch_size",
                    "preferred_timeline",
                    "message",
                )
            },
        ),
        (
            "Pipeline",
            {"fields": ("status", "internal_notes", "follow_up_date")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at")},
        ),
    )


# ── Workshop Registration ─────────────────────────────────────────────


@admin.register(WorkshopRegistration)
class WorkshopRegistrationAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "email",
        "workshop",
        "organization",
        "attended",
        "registered_at",
    ]
    list_filter = ["attended", "workshop"]
    list_editable = ["attended"]
    search_fields = ["name", "email", "organization"]
    readonly_fields = ["registered_at"]
