from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from .listing_owners import normalized_email, user_owns_listing
from .models import (
    Category,
    Deal,
    FounderSurvey,
    Guide,
    JobStack,
    Lab,
    News,
    NewsletterSubscription,
    NewsUpvote,
    PricingReport,
    Review,
    SearchQuery,
    SiteConfig,
    Tool,
    ToolClick,
    ToolSource,
    ToolSubmission,
    ToolUsage,
    UserFavorite,
    Workshop,
)
from .verified_listings import overlay_verified_listing

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "avatar_url"]
        read_only_fields = ["id"]


class CategorySerializer(serializers.ModelSerializer):
    tool_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "description",
            "slug",
            "tool_count",
            "created_at",
            "updated_at",
        ]

    def get_tool_count(self, obj):
        from .hygiene.visibility import publishable_q

        return obj.tools.filter(publishable_q()).count()


class ToolSitemapSerializer(serializers.ModelSerializer):
    """Compact payload for sitemap generation. Slug + lastmod only."""

    class Meta:
        model = Tool
        fields = ["slug", "updated_at"]


class ToolAssessmentSerializerMixin(serializers.Serializer):
    rating_status = serializers.SerializerMethodField()
    security_status = serializers.SerializerMethodField()
    # Mirrors frontend isToolAssessedForIndex — provisional+ editorial coverage.
    assessed = serializers.SerializerMethodField()

    def get_rating_status(self, obj):
        return obj.get_rating_status()

    def get_security_status(self, obj):
        return obj.get_security_status()

    def get_assessed(self, obj):
        from api.ratings import RATING_MIN_PROVISIONAL

        return int(obj.criteria_completed or 0) >= RATING_MIN_PROVISIONAL


class ToolSourceSerializer(serializers.ModelSerializer):
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = ToolSource
        fields = [
            "source",
            "source_label",
            "label",
            "url",
            "external_id",
            "observed_at",
        ]


class ToolListSerializer(ToolAssessmentSerializerMixin, serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)
    sources = ToolSourceSerializer(
        source="source_references", many=True, read_only=True
    )
    similarity = serializers.FloatField(read_only=True, required=False)
    pricing_inr = serializers.SerializerMethodField()
    pricing_inr_with_gst = serializers.SerializerMethodField()

    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "slug",
            "short_description",
            "logo_url",
            "website",
            "categories",
            "sources",
            "pricing_type",
            "pricing_models",
            "pricing_from",
            "free_tier_available",
            "free_trial_days",
            "tags",
            "use_cases",
            "rating",
            "review_count",
            "views_count",
            "entry_type",
            "popularity_score",
            "verified",
            "is_featured",
            "startup_friendly",
            "similarity",
            "pricing_inr_override",
            "pricing_has_india_plan",
            "gst_applicable",
            "pricing_inr",
            "pricing_inr_with_gst",
            "track",
            "criteria_completed",
            "overall_score",
            "security_criterion_score",
            "assessment_detail",
            "last_assessed_at",
            "rating_status",
            "security_status",
            "assessed",
            "created_at",
            "updated_at",
        ]

    def _get_exchange_rate(self):
        """Get cached exchange rate from SiteConfig."""
        if not hasattr(self, "_exchange_rate_cache"):
            try:
                config = SiteConfig.objects.get(key="EXCHANGE_RATE_USD_INR")
                self._exchange_rate_cache = float(config.value)
            except (SiteConfig.DoesNotExist, ValueError):
                self._exchange_rate_cache = 83.5
        return self._exchange_rate_cache

    def _get_gst_rate(self):
        """Get cached GST rate from SiteConfig."""
        if not hasattr(self, "_gst_rate_cache"):
            try:
                config = SiteConfig.objects.get(key="GST_RATE")
                self._gst_rate_cache = float(config.value)
            except (SiteConfig.DoesNotExist, ValueError):
                self._gst_rate_cache = 0.18
        return self._gst_rate_cache

    def get_pricing_inr(self, obj):
        if obj.pricing_inr_override is not None:
            value = round(float(obj.pricing_inr_override))
        elif obj.pricing_from is not None:
            value = round(float(obj.pricing_from) * self._get_exchange_rate())
        else:
            return None
        return value if value > 0 else None

    def get_pricing_inr_with_gst(self, obj):
        inr_price = self.get_pricing_inr(obj)
        if inr_price is not None and obj.gst_applicable:
            gst_rate = self._get_gst_rate()
            return round(inr_price * (1 + gst_rate))
        return inr_price

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return overlay_verified_listing(
            instance,
            data,
            exchange_rate=self._get_exchange_rate(),
            gst_rate=self._get_gst_rate(),
        )


class ToolDetailSerializer(ToolAssessmentSerializerMixin, serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )
    alternatives = ToolListSerializer(many=True, read_only=True)
    sources = ToolSourceSerializer(
        source="source_references", many=True, read_only=True
    )
    pricing_inr = serializers.SerializerMethodField()
    pricing_inr_with_gst = serializers.SerializerMethodField()

    class Meta:
        model = Tool
        exclude = ["embedding"]
        read_only_fields = [
            "created_at",
            "updated_at",
            "rating",
            "review_count",
            "views_count",
            "rating_status",
            "security_status",
            "last_assessed_at",
            "criteria_completed",
            "overall_score",
            "security_criterion_score",
            "assessment_detail",
            "track",
        ]

    def _get_exchange_rate(self):
        """Get cached exchange rate from SiteConfig."""
        if not hasattr(self, "_exchange_rate_cache"):
            try:
                config = SiteConfig.objects.get(key="EXCHANGE_RATE_USD_INR")
                self._exchange_rate_cache = float(config.value)
            except (SiteConfig.DoesNotExist, ValueError):
                self._exchange_rate_cache = 83.5
        return self._exchange_rate_cache

    def _get_gst_rate(self):
        """Get cached GST rate from SiteConfig."""
        if not hasattr(self, "_gst_rate_cache"):
            try:
                config = SiteConfig.objects.get(key="GST_RATE")
                self._gst_rate_cache = float(config.value)
            except (SiteConfig.DoesNotExist, ValueError):
                self._gst_rate_cache = 0.18
        return self._gst_rate_cache

    def get_pricing_inr(self, obj):
        if obj.pricing_inr_override is not None:
            value = round(float(obj.pricing_inr_override))
        elif obj.pricing_from is not None:
            value = round(float(obj.pricing_from) * self._get_exchange_rate())
        else:
            return None
        return value if value > 0 else None

    def get_pricing_inr_with_gst(self, obj):
        inr_price = self.get_pricing_inr(obj)
        if inr_price is not None and obj.gst_applicable:
            gst_rate = self._get_gst_rate()
            return round(inr_price * (1 + gst_rate))
        return inr_price

    def to_representation(self, instance):
        """Override to show full category details in response"""
        data = super().to_representation(instance)
        data["categories"] = CategorySerializer(
            instance.categories.all(), many=True
        ).data
        data = overlay_verified_listing(
            instance,
            data,
            exchange_rate=self._get_exchange_rate(),
            gst_rate=self._get_gst_rate(),
        )
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        data["can_edit"] = user_owns_listing(user, instance)
        return data


FOUNDER_EDITABLE_FIELDS = (
    "name",
    "short_description",
    "description",
    "website",
    "logo_url",
    "video_demo_url",
    "features",
    "use_cases",
    "startup_benefits",
    "pricing_models",
    "pricing_tiers",
    "pricing_from",
    "pricing_type",
    "free_tier_available",
)


class FounderToolUpdateSerializer(serializers.ModelSerializer):
    """Vendor-owned fields only. Editorial scores and flags stay staff-only."""

    class Meta:
        model = Tool
        fields = list(FOUNDER_EDITABLE_FIELDS)
        extra_kwargs = {
            "website": {"required": False, "allow_blank": True, "allow_null": True},
            "logo_url": {"required": False, "allow_blank": True, "allow_null": True},
            "video_demo_url": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "short_description": {"required": False, "allow_blank": True},
            "startup_benefits": {"required": False, "allow_blank": True},
        }

    def validate_website(self, value):
        return value or None

    def validate_logo_url(self, value):
        return value or None

    def validate_video_demo_url(self, value):
        return value or None

    def update(self, instance, validated_data):
        previous_name = instance.name
        tool = super().update(instance, validated_data)
        request = self.context.get("request")
        email = normalized_email(getattr(request, "user", None) if request else None)
        if email:
            ToolSubmission.objects.filter(
                Q(approved_tool=tool) | Q(name=previous_name),
                submitter_email__iexact=email,
                status="approved",
            ).update(
                name=tool.name,
                description=tool.description,
                short_description=tool.short_description or "",
                website=tool.website or "",
                logo_url=tool.logo_url or "",
            )
        return tool

    def to_representation(self, instance):
        return ToolDetailSerializer(instance, context=self.context).data


class ReviewSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)

    class Meta:
        model = Review
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "helpful_count", "pros", "cons"]


class DealSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)
    tool_logo = serializers.URLField(source="tool.logo_url", read_only=True)

    class Meta:
        model = Deal
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "claims_count"]


class NewsListSerializer(serializers.ModelSerializer):
    has_upvoted = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "featured_image",
            "author",
            "category",
            "tags",
            "reading_time",
            "views_count",
            "upvote_count",
            "has_upvoted",
            "is_featured",
            "published_at",
        ]

    def get_has_upvoted(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        if request.user.is_authenticated:
            return obj.upvotes.filter(user=request.user).exists()
        session_id = request.headers.get("X-Session-ID", "")
        if session_id:
            return obj.upvotes.filter(session_id=session_id).exists()
        return False


class NewsDetailSerializer(serializers.ModelSerializer):
    related_tools = ToolListSerializer(many=True, read_only=True)
    has_upvoted = serializers.SerializerMethodField()

    class Meta:
        model = News
        exclude = ["is_published"]
        read_only_fields = [
            "created_at",
            "updated_at",
            "published_at",
            "views_count",
            "upvote_count",
            "reading_time",
        ]

    def get_has_upvoted(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        if request.user.is_authenticated:
            return obj.upvotes.filter(user=request.user).exists()
        session_id = request.headers.get("X-Session-ID", "")
        if session_id:
            return obj.upvotes.filter(session_id=session_id).exists()
        return False


class NewsUpvoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsUpvote
        fields = ["id", "news", "user", "session_id", "created_at"]
        read_only_fields = ["created_at", "user"]


class NewsletterSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscription
        fields = ["email", "source"]


class ToolSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolSubmission
        fields = [
            "id",
            "name",
            "description",
            "website",
            "submitter_email",
            "submitter_name",
            "logo_url",
            "short_description",
            "categories",
            "pricing_info",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class FounderSurveySerializer(serializers.ModelSerializer):
    class Meta:
        model = FounderSurvey
        fields = [
            "name",
            "startup",
            "stage",
            "time_wasting_task",
            "area",
            "hours_per_week",
            "pain_score",
            "tried_to_solve",
            "freed_time_use",
            "willingness_to_pay",
            "contact",
        ]


class UserFavoriteSerializer(serializers.ModelSerializer):
    tool = ToolListSerializer(read_only=True)

    class Meta:
        model = UserFavorite
        fields = "__all__"
        read_only_fields = ["created_at"]


class JobStackSerializer(serializers.ModelSerializer):
    url_path = serializers.SerializerMethodField()

    class Meta:
        model = JobStack
        fields = [
            "public_id",
            "query",
            "title",
            "blurb",
            "cash_out",
            "source",
            "lanes",
            "created_at",
            "url_path",
        ]
        read_only_fields = ["public_id", "created_at"]

    def get_url_path(self, obj):
        return f"/stack/{obj.public_id}"


class ToolUsageSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)

    class Meta:
        model = ToolUsage
        fields = ["id", "tool", "tool_name", "session_id", "created_at"]
        read_only_fields = ["created_at"]


class SearchQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchQuery
        fields = ["id", "query", "session_id", "results_count", "filters", "created_at"]
        read_only_fields = ["created_at"]


class ToolClickSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)

    class Meta:
        model = ToolClick
        fields = [
            "id",
            "tool",
            "tool_name",
            "action",
            "session_id",
            "referrer",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class TrendingToolSerializer(
    ToolAssessmentSerializerMixin, serializers.ModelSerializer
):
    categories = CategorySerializer(many=True, read_only=True)
    usage_count = serializers.IntegerField(read_only=True)
    click_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "slug",
            "short_description",
            "logo_url",
            "website",
            "categories",
            "rating",
            "review_count",
            "views_count",
            "usage_count",
            "click_count",
            "is_featured",
            "criteria_completed",
            "overall_score",
            "security_criterion_score",
            "assessment_detail",
            "last_assessed_at",
            "rating_status",
            "security_status",
            "assessed",
        ]


class SiteConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteConfig
        fields = ["key", "value", "description", "updated_at"]
        read_only_fields = ["updated_at"]


class PricingReportSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source="tool.name", read_only=True)

    class Meta:
        model = PricingReport
        fields = [
            "id",
            "tool",
            "tool_name",
            "reported_by_email",
            "session_id",
            "message",
            "created_at",
        ]
        read_only_fields = ["created_at"]


# --- Learning Content Serializers ---


class LearningContentListSerializer(serializers.Serializer):
    """Shared list serializer for Guides, Labs, and Workshops."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField()
    slug = serializers.SlugField()
    short_description = serializers.CharField()
    featured_image = serializers.URLField()
    author = serializers.CharField()
    difficulty = serializers.CharField()
    estimated_time = serializers.CharField()
    category = serializers.CharField()
    audience = serializers.CharField()
    tools_used = ToolListSerializer(many=True, read_only=True)
    pricing = serializers.CharField()
    price_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_featured = serializers.BooleanField()
    last_updated = serializers.DateTimeField()
    published_at = serializers.DateTimeField()


class GuideListSerializer(LearningContentListSerializer):
    class Meta:
        model = Guide
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "is_featured",
            "last_updated",
            "published_at",
        ]


class GuideDetailSerializer(serializers.ModelSerializer):
    tools_used = ToolListSerializer(many=True, read_only=True)

    class Meta:
        model = Guide
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "content",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "meta_title",
            "meta_description",
            "is_published",
            "is_featured",
            "last_updated",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class LabListSerializer(LearningContentListSerializer):
    class Meta:
        model = Lab
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "is_featured",
            "last_updated",
            "published_at",
        ]


class LabDetailSerializer(serializers.ModelSerializer):
    tools_used = ToolListSerializer(many=True, read_only=True)

    class Meta:
        model = Lab
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "content",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "meta_title",
            "meta_description",
            "is_published",
            "is_featured",
            "last_updated",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class WorkshopListSerializer(LearningContentListSerializer):
    class Meta:
        model = Workshop
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "is_featured",
            "last_updated",
            "published_at",
        ]


class WorkshopDetailSerializer(serializers.ModelSerializer):
    tools_used = ToolListSerializer(many=True, read_only=True)

    class Meta:
        model = Workshop
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "content",
            "featured_image",
            "author",
            "difficulty",
            "estimated_time",
            "category",
            "audience",
            "tools_used",
            "pricing",
            "price_amount",
            "meta_title",
            "meta_description",
            "is_published",
            "is_featured",
            "last_updated",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
