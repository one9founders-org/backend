from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.hashers import make_password
from rest_framework import status

User = get_user_model()

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    email = request.data.get('email')
    password = request.data.get('password')
    name = request.data.get('name')
    
    if not email or not password:
        return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if User.objects.filter(email=email).exists():
        return Response({'error': 'User already exists'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.create(
            email=email,
            username=email,
            first_name=name or '',
            password=make_password(password)
        )
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'id': user.id,
            'email': user.email,
            'name': user.first_name,
            'token': token.key
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
    
    user = authenticate(username=email, password=password)
    if user:
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'id': user.id,
            'email': user.email,
            'name': user.first_name,
            'token': token.key
        })
    else:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth(request):
    email = request.data.get('email')
    name = request.data.get('name')
    google_id = request.data.get('google_id')
    
    if not email:
        return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': name or '',
                'is_active': True
            }
        )
        
        if not created and name:
            user.first_name = name
            user.save()
        
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'id': user.id,
            'email': user.email,
            'name': user.first_name,
            'token': token.key
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)