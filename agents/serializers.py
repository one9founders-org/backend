from rest_framework import serializers

from .models import AgentCategory, AIAgent


def popularity_payload(score):
    """Do not present an out-of-range source signal as a 0–100 score."""
    try:
        value = int(score or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return {"state": "unavailable", "value": None}
    if value > 100:
        return {"state": "unbounded", "value": value}
    return {"state": "bounded", "value": value}


def display_access_label(agent):
    access = (agent.access or "").strip()
    if access == "Open Source" and not (agent.github_url or "").strip():
        return None
    return access or None


class AgentListSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugField(source="category.slug", read_only=True)
    popularity = serializers.SerializerMethodField()
    display_access = serializers.SerializerMethodField()

    class Meta:
        model = AIAgent
        fields = [
            "slug",
            "name",
            "category_name",
            "category_slug",
            "industry",
            "access",
            "pricing_model",
            "short_description",
            "logo_url",
            "popularity_score",
            "upvotes",
            "views",
            "average_rating",
            "review_count",
            "is_featured",
            "website",
            "github_url",
            "popularity",
            "display_access",
        ]

    def get_popularity(self, obj):
        return popularity_payload(obj.popularity_score)

    def get_display_access(self, obj):
        return display_access_label(obj)


class AgentDetailSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugField(source="category.slug", read_only=True)
    popularity = serializers.SerializerMethodField()
    display_access = serializers.SerializerMethodField()

    class Meta:
        model = AIAgent
        fields = "__all__"

    def get_popularity(self, obj):
        return popularity_payload(obj.popularity_score)

    def get_display_access(self, obj):
        return display_access_label(obj)


class AgentCategoryTopAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAgent
        fields = ["name", "logo_url"]


class AgentCategorySerializer(serializers.ModelSerializer):
    top_agents = serializers.SerializerMethodField()

    class Meta:
        model = AgentCategory
        fields = [
            "slug",
            "label",
            "agent_count",
            "growth_rate",
            "new_agents_30d",
            "top_agents",
        ]

    def get_top_agents(self, obj):
        agents = getattr(obj, "prefetched_agents", None)
        if agents is None:
            agents = obj.agents.order_by("-popularity_score")[:5]
        else:
            agents = agents[:5]
        return AgentCategoryTopAgentSerializer(agents, many=True).data
