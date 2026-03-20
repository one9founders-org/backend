from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    Category,
    Deal,
    Guide,
    Lab,
    News,
    NewsletterSubscription,
    NewsUpvote,
    Review,
    SearchQuery,
    Tool,
    ToolClick,
    ToolSubmission,
    ToolUsage,
    UserFavorite,
    Workshop,
)

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
        return obj.tools.filter(is_active=True).count()


class ToolListSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)
    similarity = serializers.FloatField(read_only=True, required=False)

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
            "verified",
            "is_featured",
            "startup_friendly",
            "security_score",
            "security_assessed_at",
            "similarity",
        ]
        read_only_fields = [
            "security_score",
            "security_assessed_at",
        ]


class ToolDetailSerializer(serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )
    alternatives = ToolListSerializer(many=True, read_only=True)

    class Meta:
        model = Tool
        exclude = ["embedding"]
        read_only_fields = [
            "created_at",
            "updated_at",
            "rating",
            "review_count",
            "views_count",
            "security_score",
            "security_assessed_at",
        ]

    def to_representation(self, instance):
        """Override to show full category details in response"""
        data = super().to_representation(instance)
        data["categories"] = CategorySerializer(
            instance.categories.all(), many=True
        ).data
        return data


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
    description = serializers.CharField(source="excerpt", read_only=True)
    date = serializers.DateTimeField(source="published_at", read_only=True)
    image = serializers.URLField(source="featured_image", read_only=True)
    read_time = serializers.SerializerMethodField()
    has_upvoted = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "image",
            "author",
            "category",
            "tags",
            "read_time",
            "views_count",
            "upvote_count",
            "has_upvoted",
            "is_featured",
            "date",
        ]

    def get_read_time(self, obj):
        return f"{obj.reading_time} min read"

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
    description = serializers.CharField(source="excerpt", read_only=True)
    date = serializers.DateTimeField(source="published_at", read_only=True)
    image = serializers.URLField(source="featured_image", read_only=True)
    read_time = serializers.SerializerMethodField()
    has_upvoted = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "content",
            "image",
            "author",
            "category",
            "tags",
            "read_time",
            "views_count",
            "upvote_count",
            "has_upvoted",
            "is_featured",
            "date",
            "related_tools",
            "created_at",
            "updated_at",
        ]

    def get_read_time(self, obj):
        return f"{obj.reading_time} min read"

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


class UserFavoriteSerializer(serializers.ModelSerializer):
    tool = ToolListSerializer(read_only=True)

    class Meta:
        model = UserFavorite
        fields = "__all__"
        read_only_fields = ["created_at"]


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


class TrendingToolSerializer(serializers.ModelSerializer):
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
        ]


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


# Smart Search Serializers


class SmartSearchToolSerializer(ToolListSerializer):
    """Extended tool serializer with match context for smart search results."""

    match_reason = serializers.CharField(read_only=True, required=False)
    relevance_score = serializers.FloatField(read_only=True, required=False)

    class Meta(ToolListSerializer.Meta):
        fields = ToolListSerializer.Meta.fields + ["match_reason", "relevance_score"]


class ParsedIntentSerializer(serializers.Serializer):
    semantic_query = serializers.CharField()
    filters = serializers.DictField(required=False)
    sort_by = serializers.CharField(required=False, default="relevance")
    explanation = serializers.CharField(required=False)


class SmartSearchResponseSerializer(serializers.Serializer):
    """Serializer for the standard smart search response."""

    mode = serializers.CharField()
    parsed_intent = ParsedIntentSerializer()
    results = serializers.ListField(child=serializers.DictField())
    total_results = serializers.IntegerField()
    suggestions = serializers.ListField(child=serializers.CharField(), required=False)


class TaskStepSerializer(serializers.Serializer):
    """Serializer for a single step in a Tech Stack Recipe."""

    step = serializers.IntegerField()
    task = serializers.CharField()
    description = serializers.CharField()
    recommended_tools = serializers.ListField(child=serializers.DictField())
    tool_count = serializers.IntegerField()


class TaskRecipeResponseSerializer(serializers.Serializer):
    """Serializer for the full task decomposition / Tech Stack Recipe response."""

    mode = serializers.CharField()
    goal = serializers.CharField()
    parsed_intent = ParsedIntentSerializer()
    estimated_monthly_budget = serializers.CharField(required=False)
    time_to_setup = serializers.CharField(required=False)
    steps = TaskStepSerializer(many=True)
    total_steps = serializers.IntegerField()
    total_tools_recommended = serializers.IntegerField()
