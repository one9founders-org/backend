from rest_framework import serializers

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

# ── Lookup / Taxonomy ──────────────────────────────────────────────────


class CourseCategorySerializer(serializers.ModelSerializer):
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = CourseCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "order",
            "course_count",
        ]

    def get_course_count(self, obj):
        return obj.courses.filter(status="published").count()


class AudienceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudienceType
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "landing_page_url",
            "order",
        ]


class InstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instructor
        fields = [
            "id",
            "name",
            "slug",
            "title",
            "bio",
            "short_bio",
            "photo",
            "linkedin_url",
            "twitter_url",
        ]


# ── Course ─────────────────────────────────────────────────────────────


class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ["id", "title", "description", "order", "duration_description"]


class CourseFAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseFAQ
        fields = ["id", "question", "answer", "order"]


class CourseListSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    audiences = AudienceTypeSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "subtitle",
            "short_description",
            "featured_image",
            "category",
            "audiences",
            "difficulty",
            "format",
            "status",
            "duration_weeks",
            "hours_per_week",
            "has_certificate",
            "language",
            "has_hindi_support",
            "is_featured",
            "interest_count",
            "rating",
        ]


class CourseDetailSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    audiences = AudienceTypeSerializer(many=True, read_only=True)
    instructors = InstructorSerializer(many=True, read_only=True)
    modules = CourseModuleSerializer(many=True, read_only=True)
    faqs = CourseFAQSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        exclude = ["iitb_eo_link"]
        read_only_fields = [
            "interest_count",
            "rating",
            "created_at",
            "updated_at",
        ]


# ── Guide ──────────────────────────────────────────────────────────────


class EducationGuideListSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    author = InstructorSerializer(read_only=True)

    class Meta:
        model = EducationGuide
        fields = [
            "id",
            "title",
            "slug",
            "subtitle",
            "excerpt",
            "featured_image",
            "category",
            "author",
            "difficulty",
            "status",
            "read_time_minutes",
            "is_featured",
            "view_count",
            "published_at",
        ]


class EducationGuideDetailSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    author = InstructorSerializer(read_only=True)
    audiences = AudienceTypeSerializer(many=True, read_only=True)
    related_course = CourseListSerializer(read_only=True)

    class Meta:
        model = EducationGuide
        fields = [
            "id",
            "title",
            "slug",
            "subtitle",
            "content",
            "excerpt",
            "featured_image",
            "category",
            "author",
            "audiences",
            "difficulty",
            "status",
            "read_time_minutes",
            "tools_mentioned",
            "related_course",
            "meta_title",
            "meta_description",
            "is_featured",
            "view_count",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["view_count", "created_at", "updated_at"]


# ── Workshop ───────────────────────────────────────────────────────────


class EducationWorkshopListSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    instructor = InstructorSerializer(read_only=True)

    class Meta:
        model = EducationWorkshop
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "date",
            "duration_minutes",
            "timezone",
            "format",
            "status",
            "category",
            "instructor",
            "max_participants",
            "registration_count",
            "is_featured",
        ]


class EducationWorkshopDetailSerializer(serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    instructor = InstructorSerializer(read_only=True)
    audiences = AudienceTypeSerializer(many=True, read_only=True)

    class Meta:
        model = EducationWorkshop
        exclude = ["meeting_link"]
        read_only_fields = [
            "registration_count",
            "created_at",
            "updated_at",
        ]


# ── Learning Path ──────────────────────────────────────────────────────


class LearningPathModuleSerializer(serializers.ModelSerializer):
    courses = CourseListSerializer(many=True, read_only=True)
    guides = EducationGuideListSerializer(many=True, read_only=True)
    workshops = EducationWorkshopListSerializer(many=True, read_only=True)

    class Meta:
        model = LearningPathModule
        fields = [
            "id",
            "title",
            "description",
            "order",
            "courses",
            "guides",
            "workshops",
        ]


class LearningPathListSerializer(serializers.ModelSerializer):
    audience = AudienceTypeSerializer(read_only=True)

    class Meta:
        model = LearningPath
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "icon",
            "audience",
            "estimated_duration",
            "order",
        ]


class LearningPathDetailSerializer(serializers.ModelSerializer):
    audience = AudienceTypeSerializer(read_only=True)
    modules = LearningPathModuleSerializer(many=True, read_only=True)

    class Meta:
        model = LearningPath
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "short_description",
            "icon",
            "audience",
            "estimated_duration",
            "order",
            "modules",
        ]


# ── Landing Page ───────────────────────────────────────────────────────


class LandingPageSerializer(serializers.ModelSerializer):
    featured_courses = CourseListSerializer(many=True, read_only=True)

    class Meta:
        model = LandingPage
        fields = [
            "id",
            "page_type",
            "hero_title",
            "hero_subtitle",
            "hero_cta_text",
            "hero_cta_url",
            "hero_image",
            "pitch_title",
            "pitch_content",
            "content_blocks",
            "featured_courses",
            "meta_title",
            "meta_description",
            "is_active",
        ]


# ── Inquiry / Registration (write-only) ───────────────────────────────


class CourseInquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseInquiry
        fields = [
            "id",
            "course",
            "workshop",
            "learning_path",
            "source_page",
            "name",
            "email",
            "phone",
            "city",
            "current_role",
            "message",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class OrganizationInquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationInquiry
        fields = [
            "id",
            "inquiry_type",
            "name",
            "email",
            "phone",
            "organization",
            "role",
            "city",
            "estimated_batch_size",
            "preferred_timeline",
            "message",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class WorkshopRegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopRegistration
        fields = [
            "id",
            "workshop",
            "name",
            "email",
            "phone",
            "organization",
            "registered_at",
        ]
        read_only_fields = ["id", "registered_at"]
