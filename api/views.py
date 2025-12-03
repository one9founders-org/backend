from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.db.models import Q
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.hashers import make_password
import google.generativeai as genai
from django.conf import settings
from .models import Tool, Category, Review, Deal, News, NewsletterSubscription, ToolSubmission
from .serializers import (
    ToolSerializer, CategorySerializer, ReviewSerializer, 
    DealSerializer, NewsSerializer, NewsletterSubscriptionSerializer,
    ToolSubmissionSerializer, UserSerializer
)

User = get_user_model()
genai.configure(api_key=settings.GEMINI_API_KEY)

class ToolViewSet(viewsets.ModelViewSet):
    queryset = Tool.objects.filter(is_active=True)
    serializer_class = ToolSerializer
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['post'])
    def search(self, request):
        query = request.data.get('query', '')
        if not query:
            return Response([])
        
        # Exact name match
        exact_matches = list(Tool.objects.filter(
            name__icontains=query,
            is_active=True
        )[:5].values())
        
        # Semantic search
        try:
            model = genai.GenerativeModel('gemini-pro')
            embedding_model = genai.embed_content(
                model="models/text-embedding-004",
                content=query
            )
            embedding = embedding_model['embedding']
            
            # Use pgvector for similarity search
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description, category, url, image_url, 
                           pricing, pricing_model, pricing_from, billing_frequency,
                           free_trial_days, tags, video_demo_url, use_cases,
                           rating, review_count, verified, featured, is_featured,
                           launch_date, company_size, integrations,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM tools
                    WHERE is_active = TRUE 
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> %s::vector) > 0.3
                    ORDER BY embedding <=> %s::vector
                    LIMIT 10
                """, [embedding, embedding, embedding])
                
                columns = [col[0] for col in cursor.description]
                semantic_matches = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Semantic search error: {e}")
            semantic_matches = []
        
        # Combine results
        exact_ids = {tool['id'] for tool in exact_matches}
        for tool in exact_matches:
            tool['similarity'] = 10.0
        
        combined = exact_matches + [
            tool for tool in semantic_matches 
            if tool['id'] not in exact_ids
        ]
        
        combined.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        return Response(combined[:10])
    
    @action(detail=False, methods=['post'])
    def add_tool(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # Generate embedding
            try:
                text = f"{request.data['name']} - {request.data['description']}"
                embedding_result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text
                )
                serializer.save(embedding=embedding_result['embedding'])
                return Response({'success': True}, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = Review.objects.all()
        tool_id = self.request.query_params.get('tool_id')
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)
        return queryset.order_by('-created_at')

class DealViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Deal.objects.filter(is_active=True).order_by('-featured_deal', '-created_at')
    serializer_class = DealSerializer
    permission_classes = [AllowAny]

class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = News.objects.filter(is_published=True).order_by('-published_at')
    serializer_class = NewsSerializer
    permission_classes = [AllowAny]

@api_view(['POST'])
@permission_classes([AllowAny])
def subscribe_newsletter(request):
    serializer = NewsletterSubscriptionSerializer(data=request.data)
    if serializer.is_valid():
        try:
            serializer.save()
            return Response({'success': True}, status=status.HTTP_201_CREATED)
        except Exception as e:
            if 'unique' in str(e).lower():
                return Response({'success': False, 'error': 'Email already subscribed'}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def submit_tool(request):
    serializer = ToolSubmissionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def seed_database(request):
    portfolio_data = [
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
            "featured": True
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
            "featured": True
        }
    ]
    
    try:
        for tool_data in portfolio_data:
            text = f"{tool_data['name']} - {tool_data['description']}"
            embedding_result = genai.embed_content(
                model="models/text-embedding-004",
                content=text
            )
            tool_data['embedding'] = embedding_result['embedding']
            Tool.objects.create(**tool_data)
        
        return Response({'success': True}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
