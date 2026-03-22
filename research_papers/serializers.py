from rest_framework import serializers

from .models import Author, Paper


class PaperListSerializer(serializers.ModelSerializer):
    has_code = serializers.SerializerMethodField()
    authors_display = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = [
            "arxiv_id",
            "title",
            "authors",
            "authors_display",
            "published_at",
            "ai_summary",
            "ai_tags",
            "ai_difficulty",
            "hf_upvotes",
            "code_url",
            "has_code",
            "is_trending",
            "categories",
        ]

    def get_has_code(self, obj):
        return bool(obj.code_url)

    def get_authors_display(self, obj):
        authors = obj.authors or []
        if len(authors) <= 3:
            return ", ".join(authors)
        return ", ".join(authors[:3]) + " et al."


class PaperDetailSerializer(serializers.ModelSerializer):
    has_code = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = [
            "arxiv_id",
            "title",
            "abstract",
            "authors",
            "categories",
            "published_at",
            "updated_at_arxiv",
            "pdf_url",
            "arxiv_url",
            "hf_url",
            "code_url",
            "demo_url",
            "hf_upvotes",
            "citation_count",
            "ai_summary",
            "ai_tags",
            "ai_difficulty",
            "is_enriched",
            "is_trending",
            "created_at",
            "has_code",
        ]

    def get_has_code(self, obj):
        return bool(obj.code_url)


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "paper_count", "first_seen", "last_seen"]
