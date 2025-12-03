from django.contrib import admin
from .models import (
    User, Category, Tool, Review, ToolReview, 
    UserFavorite, ToolSubmission, NewsletterSubscription, Deal, News
)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_active']
    search_fields = ['email', 'username']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'rating', 'review_count', 'is_featured', 'is_active']
    list_filter = ['is_active', 'is_featured', 'verified', 'category']
    search_fields = ['name', 'description']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['tool', 'user_name', 'rating', 'created_at']
    list_filter = ['rating', 'verified_purchase']
    search_fields = ['user_name', 'title', 'comment']

@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ['tool_name', 'discount_percentage', 'expiry_date', 'featured_deal', 'is_active']
    list_filter = ['featured_deal', 'is_active']

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'is_published', 'published_at']
    list_filter = ['is_published', 'category']
    search_fields = ['title', 'content']

@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['email', 'source', 'is_active', 'created_at']
    list_filter = ['is_active', 'source']

@admin.register(ToolSubmission)
class ToolSubmissionAdmin(admin.ModelAdmin):
    list_display = ['name', 'submitter_email', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['name', 'submitter_email']

admin.site.register(ToolReview)
admin.site.register(UserFavorite)
