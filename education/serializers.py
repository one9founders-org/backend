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

# -- Nested / lightweight serializers -----------------------------------------


class CategoryNameSlugSerializer(serializers.ModelSerializer):
    """Lightweight category serializer for nested use."""

    class Meta:
        model = CourseCategory
        fields = ["name", "slug"]


class AudienceNameSlugSerializer(serializers.ModelSerializer):
    """Lightweight audience serializer for nested use."""

    class Meta:
        model = AudienceType
        fields = ["name", "slug"]


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


class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ["id", "title", "description", "order", "duration_description"]


class CourseFAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseFAQ
        fields = ["id", "question", "answer", "order"]


# -- Course serializers -------------------------------------------------------


class CourseListSerializer(serializers.ModelSerializer):
    category = CategoryNameSlugSerializer(read_only=True)
    audiences = AudienceNameSlugSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "difficulty",
            "format",
            "duration_weeks",
            "has_certificate",
            "is_featured",
            "next_cohort_date",
            "featured_image",
            "category",
            "audiences",
        ]


class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategoryNameSlugSerializer(read_only=True)
    audiences = AudienceNameSlugSerializer(many=True, read_only=True)
    instructors = InstructorSerializer(many=True, read_only=True)
    modules = CourseModuleSerializer(many=True, read_only=True)
    faqs = CourseFAQSerializer(many=True, read_only=True)
    related_guides = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "subtitle",
            "description",
            "short_description",
            "featured_image",
            "intro_video_url",
            "difficulty",
            "format",
            "status",
            "duration_weeks",
            "hours_per_week",
            "total_lessons",
            "next_cohort_date",
            "schedule_description",
            "whats_included",
            "tools_mentioned",
            "certificate_description",
            "has_certificate",
            "language",
            "has_hindi_support",
            "meta_title",
            "meta_description",
            "is_featured",
            "rating",
            "category",
            "audiences",
            "instructors",
            "modules",
            "faqs",
            "related_guides",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_related_guides(self, obj):
        guides = obj.related_guides.filter(status="published")[:5]
        return [{"title": g.title, "slug": g.slug} for g in guides]


# -- Guide serializers --------------------------------------------------------


class GuideListSerializer(serializers.ModelSerializer):
    category = CategoryNameSlugSerializer(read_only=True)
    audiences = AudienceNameSlugSerializer(many=True, read_only=True)

    class Meta:
        model = EducationGuide
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "difficulty",
            "read_time_minutes",
            "is_featured",
            "published_at",
            "featured_image",
            "category",
            "audiences",
        ]


class GuideDetailSerializer(serializers.ModelSerializer):
    category = CategoryNameSlugSerializer(read_only=True)
    audiences = AudienceNameSlugSerializer(many=True, read_only=True)
    author = InstructorSerializer(read_only=True)
    related_course = serializers.SerializerMethodField()

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
            "difficulty",
            "read_time_minutes",
            "tools_mentioned",
            "meta_title",
            "meta_description",
            "is_featured",
            "published_at",
            "category",
            "audiences",
            "author",
            "related_course",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_related_course(self, obj):
        if obj.related_course:
            return {
                "title": obj.related_course.title,
                "slug": obj.related_course.slug,
            }
        return None


# -- Workshop serializers -----------------------------------------------------


class WorkshopListSerializer(serializers.ModelSerializer):
    instructor = serializers.SerializerMethodField()

    class Meta:
        model = EducationWorkshop
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "date",
            "duration_minutes",
            "format",
            "status",
            "instructor",
            "is_featured",
        ]

    def get_instructor(self, obj):
        if obj.instructor:
            return obj.instructor.name
        return None


class WorkshopDetailSerializer(serializers.ModelSerializer):
    category = CategoryNameSlugSerializer(read_only=True)
    audiences = AudienceNameSlugSerializer(many=True, read_only=True)
    instructor = InstructorSerializer(read_only=True)

    class Meta:
        model = EducationWorkshop
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "short_description",
            "date",
            "duration_minutes",
            "timezone",
            "format",
            "status",
            "platform",
            "recording_url",
            "max_participants",
            "learning_outcomes",
            "prerequisites",
            "is_featured",
            "category",
            "audiences",
            "instructor",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


# -- LearningPath serializers -------------------------------------------------


class LearningPathListSerializer(serializers.ModelSerializer):
    audience = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "estimated_duration",
            "audience",
            "icon",
        ]

    def get_audience(self, obj):
        if obj.audience:
            return obj.audience.name
        return None


class LearningPathModuleSerializer(serializers.ModelSerializer):
    courses = CourseListSerializer(many=True, read_only=True)
    guides = GuideListSerializer(many=True, read_only=True)
    workshops = WorkshopListSerializer(many=True, read_only=True)

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


class LearningPathDetailSerializer(serializers.ModelSerializer):
    audience = AudienceNameSlugSerializer(read_only=True)
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
            "estimated_duration",
            "audience",
            "modules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


# -- LandingPage serializer ---------------------------------------------------


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


# -- Write-only serializers (form submissions) --------------------------------


class CourseInquiryCreateSerializer(serializers.ModelSerializer):
    course_slug = serializers.SlugField(required=False, write_only=True)

    class Meta:
        model = CourseInquiry
        fields = [
            "name",
            "email",
            "phone",
            "city",
            "current_role",
            "message",
            "course_slug",
            "source_page",
        ]

    def validate_course_slug(self, value):
        if value:
            try:
                Course.objects.get(slug=value)
            except Course.DoesNotExist:
                raise serializers.ValidationError("Course not found.")
        return value

    def create(self, validated_data):
        course_slug = validated_data.pop("course_slug", None)
        if course_slug:
            validated_data["course"] = Course.objects.get(slug=course_slug)
        return super().create(validated_data)

    def to_representation(self, instance):
        return {
            "success": True,
            "message": "Your inquiry has been submitted successfully.",
        }


class OrganizationInquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationInquiry
        fields = [
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
        ]

    def to_representation(self, instance):
        return {
            "success": True,
            "message": "Your inquiry has been submitted successfully.",
        }


class WorkshopRegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopRegistration
        fields = [
            "name",
            "email",
            "phone",
            "organization",
        ]

    def to_representation(self, instance):
        return {
            "success": True,
            "message": "You have been registered successfully.",
        }
