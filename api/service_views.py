"""Service inquiry intake. Persists the request and does not send mail."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ServiceInquiry

OFFERS = {choice[0] for choice in ServiceInquiry.OFFER_CHOICES}


class ServiceInquirySerializer(serializers.ModelSerializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = ServiceInquiry
        fields = [
            "id",
            "offer",
            "workflow",
            "current_tools",
            "team_context",
            "desired_outcome",
            "contact_name",
            "contact_email",
            "company",
            "status",
            "created_at",
            "website",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_offer(self, value):
        if value not in OFFERS:
            raise serializers.ValidationError("Choose a listed service.")
        return value

    def validate_workflow(self, value):
        if len((value or "").strip()) < 12:
            raise serializers.ValidationError(
                "Describe the workflow or problem in a sentence or two."
            )
        return value.strip()

    def validate_desired_outcome(self, value):
        if len((value or "").strip()) < 8:
            raise serializers.ValidationError("Describe the outcome you want.")
        return value.strip()

    def validate_contact_name(self, value):
        if len((value or "").strip()) < 2:
            raise serializers.ValidationError("Enter a name.")
        return value.strip()

    def create(self, validated_data):
        validated_data.pop("website", None)
        return super().create(validated_data)


@api_view(["POST"])
@permission_classes([AllowAny])
def create_service_inquiry(request):
    serializer = ServiceInquirySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if (serializer.validated_data.get("website") or "").strip():
        return Response({"status": "received"}, status=status.HTTP_201_CREATED)

    email = serializer.validated_data["contact_email"]
    since = timezone.now() - timedelta(hours=1)
    if (
        ServiceInquiry.objects.filter(
            contact_email__iexact=email, created_at__gte=since
        ).count()
        >= 3
    ):
        return Response(
            {"detail": "Too many inquiries from this address. Try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    inquiry = serializer.save()
    return Response(
        ServiceInquirySerializer(inquiry).data, status=status.HTTP_201_CREATED
    )
