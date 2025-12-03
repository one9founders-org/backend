from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Tool, Category, Review, Deal, News, NewsletterSubscription, ToolSubmission

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'avatar_url']
        read_only_fields = ['id']

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ToolSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category_id.name', read_only=True)
    similarity = serializers.FloatField(read_only=True, required=False)
    
    class Meta:
        model = Tool
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'helpful_count']

class DealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deal
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

class NewsSerializer(serializers.ModelSerializer):
    class Meta:
        model = News
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'published_at']

class NewsletterSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscription
        fields = ['email', 'source']

class ToolSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolSubmission
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'status', 'admin_notes']
