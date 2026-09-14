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
    authors_detail = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        fields = [
            "arxiv_id",
            "title",
            "abstract",
            "authors",
            "authors_detail",
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

    def get_authors_detail(self, obj):
        author_names = obj.authors or []
        authors = Author.objects.filter(name__in=author_names).only("name", "slug")
        slugs_by_name = {author.name: author.slug for author in authors}
        return [
            {"name": name, "slug": slugs_by_name[name]}
            for name in author_names
            if name in slugs_by_name
        ]


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "slug", "paper_count", "first_seen", "last_seen"]
