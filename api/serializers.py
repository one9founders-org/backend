from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import (
    Category,
    Deal,
    News,
    NewsletterSubscription,
    Review,
    SearchQuery,
    Tool,
    ToolClick,
    ToolSubmission,
    ToolUsage,
    UserFavorite,
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
            "similarity",
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
            "is_featured",
            "published_at",
        ]


class NewsDetailSerializer(serializers.ModelSerializer):
    related_tools = ToolListSerializer(many=True, read_only=True)

    class Meta:
        model = News
        exclude = ["is_published"]
        read_only_fields = [
            "created_at",
            "updated_at",
            "published_at",
            "views_count",
            "reading_time",
        ]


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
