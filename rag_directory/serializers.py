from rest_framework import serializers

from .models import GitHubSnapshot, RagTool


class GitHubSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubSnapshot
        fields = [
            "id",
            "stars",
            "forks",
            "open_issues",
            "contributors",
            "last_commit_at",
            "latest_release",
            "snapshot_date",
        ]


class RagToolListSerializer(serializers.ModelSerializer):
    class Meta:
        model = RagTool
        fields = [
            "id",
            "slug",
            "name",
            "logo_url",
            "description",
            "category",
            "pricing_model",
            "deployment_options",
            "overall_rating",
            "github_stars",
            "featured",
            "status",
            "sdk_languages",
        ]


class RagToolDetailSerializer(serializers.ModelSerializer):
    github_snapshots = serializers.SerializerMethodField()
    stars_history = serializers.SerializerMethodField()

    class Meta:
        model = RagTool
        fields = [
            "id",
            "slug",
            "name",
            "logo_url",
            "description",
            "long_description",
            "website_url",
            "docs_url",
            "github_url",
            "github_repo",
            "category",
            "pricing_model",
            "pricing_details",
            "deployment_options",
            "sdk_languages",
            "integrations",
            "specs",
            "security_certs",
            "rating_scores",
            "overall_rating",
            "featured",
            "status",
            "github_stars",
            "github_forks",
            "last_commit_at",
            "latest_release",
            "created_at",
            "updated_at",
            "github_snapshots",
            "stars_history",
        ]

    def get_github_snapshots(self, obj):
        snapshots = obj.github_snapshots.order_by("-snapshot_date")[:12]
        return GitHubSnapshotSerializer(snapshots, many=True).data

    def get_stars_history(self, obj):
        snapshots = obj.github_snapshots.order_by("snapshot_date")[:12]
        return [
            {"date": s.snapshot_date.isoformat(), "stars": s.stars} for s in snapshots
        ]


class RagToolCompareSerializer(serializers.ModelSerializer):
    class Meta:
        model = RagTool
        fields = [
            "id",
            "slug",
            "name",
            "logo_url",
            "description",
            "category",
            "pricing_model",
            "pricing_details",
            "deployment_options",
            "sdk_languages",
            "integrations",
            "specs",
            "security_certs",
            "rating_scores",
            "overall_rating",
            "github_stars",
            "github_forks",
            "status",
        ]
