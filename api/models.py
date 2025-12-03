from django.db import models
from django.contrib.auth.models import AbstractUser
from pgvector.django import VectorField

class User(AbstractUser):
    avatar_url = models.URLField(blank=True, null=True)
    
    class Meta:
        db_table = 'users'

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'Categories'

class Tool(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=255, blank=True, null=True)
    category_id = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    url = models.URLField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    pricing = models.CharField(max_length=50, default='Unknown')
    pricing_model = models.CharField(max_length=50, blank=True, null=True)
    pricing_from = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    billing_frequency = models.CharField(max_length=50, default='Unknown')
    free_trial_days = models.IntegerField(blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    video_demo_url = models.URLField(blank=True, null=True)
    use_cases = models.JSONField(default=list, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    review_count = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    launch_date = models.DateField(blank=True, null=True)
    company_size = models.CharField(max_length=50, blank=True, null=True)
    integrations = models.JSONField(default=list, blank=True)
    embedding = VectorField(dimensions=768, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tools'
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['-rating']),
            models.Index(fields=['company_size']),
        ]

class Review(models.Model):
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name='reviews')
    user_name = models.CharField(max_length=255)
    user_email = models.EmailField(blank=True, null=True)
    rating = models.IntegerField()
    title = models.CharField(max_length=255)
    comment = models.TextField()
    pros = models.JSONField(default=list, blank=True)
    cons = models.JSONField(default=list, blank=True)
    use_case = models.TextField(blank=True, null=True)
    company_size = models.CharField(max_length=50, blank=True, null=True)
    verified_purchase = models.BooleanField(default=False)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'reviews'
        indexes = [
            models.Index(fields=['tool']),
            models.Index(fields=['-rating']),
        ]

class ToolReview(models.Model):
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    rating = models.IntegerField()
    review_text = models.TextField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tool_reviews'

class UserFavorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_favorites'
        unique_together = ('user', 'tool')

class ToolSubmission(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField()
    url = models.URLField()
    category_name = models.CharField(max_length=255, blank=True, null=True)
    submitter_email = models.EmailField(blank=True, null=True)
    submitter_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tool_submissions'

class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    source = models.CharField(max_length=50, default='homepage')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'newsletter_subscriptions'

class Deal(models.Model):
    tool_name = models.CharField(max_length=255)
    offer_title = models.CharField(max_length=255)
    tool_short_desc = models.TextField()
    image_url = models.URLField()
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.IntegerField()
    expiry_date = models.DateField()
    claims_count = models.IntegerField(default=0)
    offer_tag = models.CharField(max_length=50)
    featured_deal = models.BooleanField(default=False)
    deal_url = models.URLField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'deals'

class News(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    excerpt = models.TextField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    author = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'news'
        verbose_name_plural = 'News'
