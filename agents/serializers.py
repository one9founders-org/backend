from rest_framework import serializers

from .models import AgentCategory, AIAgent


class AgentListSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugField(source="category.slug", read_only=True)

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
        ]


class AgentDetailSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugField(source="category.slug", read_only=True)

    class Meta:
        model = AIAgent
        fields = "__all__"


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
