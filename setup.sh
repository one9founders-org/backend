#!/bin/bash

echo "🚀 Setting up One9Founders Django Backend..."

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if PostgreSQL is running
echo "🔍 Checking PostgreSQL..."
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL not found. Please install it first:"
    echo "   brew install postgresql@14"
    exit 1
fi

# Create database
echo "🗄️  Creating database..."
createdb one9founders 2>/dev/null || echo "Database already exists"

# Enable pgvector
echo "🔧 Enabling pgvector extension..."
psql one9founders -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || echo "Extension already enabled"

# Run migrations
echo "🔄 Running migrations..."
python manage.py makemigrations
python manage.py migrate

# Create superuser prompt
echo ""
echo "👤 Create a superuser account for admin access:"
python manage.py createsuperuser

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Update .env file with your credentials"
echo "2. Run: python manage.py runserver"
echo "3. Access admin at: http://localhost:8000/admin/"
echo "4. Seed data: POST to http://localhost:8000/api/seed/"
