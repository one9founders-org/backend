#!/usr/bin/env python
"""Seed database with sample tools and data"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import Tool, Deal, News, Category
from datetime import datetime, timedelta

def seed_tools():
    """Seed sample tools"""
    tools_data = [
        {
            "name": "ChatGPT",
            "description": "AI-powered conversational assistant for content creation, coding, and problem-solving",
            "category": "AI",
            "url": "https://chat.openai.com",
            "image_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=300&h=200&fit=crop",
            "pricing_model": "Freemium",
            "pricing_from": 20,
            "billing_frequency": "Monthly",
            "tags": ["conversational AI", "content creation", "coding assistant"],
            "use_cases": ["content writing", "code generation", "customer support"],
            "rating": 4.8,
            "review_count": 2847,
            "verified": True,
            "featured": True,
            "is_featured": True
        },
        {
            "name": "Midjourney",
            "description": "AI image generation platform for creating stunning visual content",
            "category": "AI",
            "url": "https://midjourney.com",
            "image_url": "https://images.unsplash.com/photo-1547036967-23d11aacaee0?w=300&h=200&fit=crop",
            "pricing_model": "Paid",
            "pricing_from": 10,
            "billing_frequency": "Monthly",
            "tags": ["image generation", "art creation", "design"],
            "use_cases": ["marketing visuals", "social media content", "concept art"],
            "rating": 4.7,
            "review_count": 1923,
            "verified": True,
            "featured": True,
            "is_featured": True
        },
        {
            "name": "Notion AI",
            "description": "Smart workspace combining notes, tasks, and AI-powered assistance",
            "category": "Productivity",
            "url": "https://notion.so",
            "image_url": "https://images.unsplash.com/photo-1611224923853-80b023f02d71?w=300&h=200&fit=crop",
            "pricing_model": "Freemium",
            "pricing_from": 8,
            "billing_frequency": "Monthly",
            "tags": ["workspace", "note-taking", "project management"],
            "use_cases": ["team collaboration", "documentation", "task management"],
            "rating": 4.6,
            "review_count": 3421,
            "verified": True
        },
        {
            "name": "GitHub Copilot",
            "description": "AI pair programming assistant that helps write code faster",
            "category": "Development",
            "url": "https://github.com/features/copilot",
            "image_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=300&h=200&fit=crop",
            "pricing_model": "Paid",
            "pricing_from": 10,
            "billing_frequency": "Monthly",
            "tags": ["code completion", "programming", "AI assistant"],
            "use_cases": ["code generation", "debugging", "learning programming"],
            "rating": 4.5,
            "review_count": 8934,
            "verified": True
        },
        {
            "name": "Grammarly",
            "description": "AI writing assistant for grammar, spelling, and style improvement",
            "category": "Writing",
            "url": "https://grammarly.com",
            "image_url": "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=300&h=200&fit=crop",
            "pricing_model": "Freemium",
            "pricing_from": 12,
            "billing_frequency": "Monthly",
            "tags": ["grammar check", "writing assistant", "proofreading"],
            "use_cases": ["email writing", "document editing", "content improvement"],
            "rating": 4.7,
            "review_count": 12847,
            "verified": True,
            "featured": True,
            "is_featured": True
        },
    ]
    
    for tool_data in tools_data:
        tool, created = Tool.objects.get_or_create(
            name=tool_data['name'],
            defaults=tool_data
        )
        if created:
            print(f"✓ Created tool: {tool.name}")
        else:
            print(f"- Tool already exists: {tool.name}")
    
    print(f"\nTotal tools: {Tool.objects.count()}")

def seed_deals():
    """Seed sample deals"""
    deals_data = [
        {
            "tool_name": "ChatGPT Pro",
            "offer_title": "Black Friday Special",
            "tool_short_desc": "Advanced AI conversation for businesses",
            "image_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400&h=300&fit=crop",
            "old_price": 40,
            "new_price": 20,
            "discount_percentage": 50,
            "expiry_date": (datetime.now() + timedelta(days=7)).date(),
            "claims_count": 1234,
            "offer_tag": "50% OFF",
            "featured_deal": True,
            "deal_url": "https://chat.openai.com/"
        },
        {
            "tool_name": "Midjourney",
            "offer_title": "Annual Plan Discount",
            "tool_short_desc": "AI image generation platform",
            "image_url": "https://images.unsplash.com/photo-1547036967-23d11aacaee0?w=400&h=300&fit=crop",
            "old_price": 120,
            "new_price": 96,
            "discount_percentage": 20,
            "expiry_date": (datetime.now() + timedelta(days=14)).date(),
            "claims_count": 567,
            "offer_tag": "20% OFF",
            "featured_deal": False,
            "deal_url": "https://midjourney.com/"
        },
    ]
    
    for deal_data in deals_data:
        deal, created = Deal.objects.get_or_create(
            tool_name=deal_data['tool_name'],
            defaults=deal_data
        )
        if created:
            print(f"✓ Created deal: {deal.tool_name}")
        else:
            print(f"- Deal already exists: {deal.tool_name}")
    
    print(f"\nTotal deals: {Deal.objects.count()}")

def seed_news():
    """Seed sample news articles"""
    news_data = [
        {
            "title": "The Future of AI Tools in 2024",
            "content": "Artificial Intelligence continues to revolutionize how we work...",
            "excerpt": "Exploring the latest trends in AI technology",
            "image_url": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800&h=400&fit=crop",
            "author": "John Doe",
            "category": "AI Trends",
            "tags": ["AI", "trends", "2024"]
        },
        {
            "title": "Top 10 Productivity Tools for Developers",
            "content": "Boost your development workflow with these amazing tools...",
            "excerpt": "Essential tools every developer should know",
            "image_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800&h=400&fit=crop",
            "author": "Jane Smith",
            "category": "Development",
            "tags": ["productivity", "development", "tools"]
        },
    ]
    
    for news_item in news_data:
        article, created = News.objects.get_or_create(
            title=news_item['title'],
            defaults=news_item
        )
        if created:
            print(f"✓ Created news: {article.title}")
        else:
            print(f"- News already exists: {article.title}")
    
    print(f"\nTotal news articles: {News.objects.count()}")

if __name__ == '__main__':
    print("🌱 Seeding database...\n")
    print("=" * 50)
    print("TOOLS")
    print("=" * 50)
    seed_tools()
    print("\n" + "=" * 50)
    print("DEALS")
    print("=" * 50)
    seed_deals()
    print("\n" + "=" * 50)
    print("NEWS")
    print("=" * 50)
    seed_news()
    print("\n✅ Database seeding complete!")
