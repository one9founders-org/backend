# One9Founders Django Backend

Complete Django backend migration from Supabase.

## Setup Instructions

### 1. Database Setup

```bash
# Install PostgreSQL (if not installed)
brew install postgresql@14

# Start PostgreSQL
brew services start postgresql@14

# Create database
createdb one9founders

# Enable pgvector extension
psql one9founders -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Environment Configuration

Copy `.env` file and update with your credentials:

```bash
cp .env .env.local
```

Update these values in `.env`:
- `DATABASE_PASSWORD`: Your PostgreSQL password
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth secret

### 3. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Seed Initial Data

```bash
# Insert default categories
python manage.py shell
>>> from api.models import Category
>>> categories = [
...     {'name': 'AI Assistant', 'slug': 'ai-assistant', 'description': 'Conversational AI and chatbots'},
...     {'name': 'Content Creation', 'slug': 'content-creation', 'description': 'AI tools for writing'},
...     {'name': 'Image Generation', 'slug': 'image-generation', 'description': 'AI-powered image creation'},
...     {'name': 'Development', 'slug': 'development', 'description': 'AI coding assistants'},
... ]
>>> for cat in categories:
...     Category.objects.get_or_create(**cat)
>>> exit()
```

### 7. Run Server

```bash
python manage.py runserver
```

Server will run at: `http://localhost:8000`

## API Endpoints

### Tools
- `GET /api/tools/` - List all tools
- `GET /api/tools/{id}/` - Get tool details
- `POST /api/tools/search/` - Semantic search
  ```json
  {"query": "AI writing assistant"}
  ```
- `POST /api/tools/add_tool/` - Add new tool
- `PUT /api/tools/{id}/` - Update tool
- `DELETE /api/tools/{id}/` - Delete tool

### Reviews
- `GET /api/reviews/?tool_id={id}` - Get reviews for tool
- `POST /api/reviews/` - Add review
  ```json
  {
    "tool_id": 1,
    "user_name": "John Doe",
    "rating": 5,
    "title": "Great tool",
    "comment": "Very helpful"
  }
  ```

### Deals
- `GET /api/deals/` - List all active deals

### News
- `GET /api/news/` - List all news articles
- `GET /api/news/{id}/` - Get news article

### Newsletter
- `POST /api/newsletter/subscribe/` - Subscribe to newsletter
  ```json
  {"email": "user@example.com", "source": "homepage"}
  ```

### Categories
- `GET /api/categories/` - List all categories

### Seed Data
- `POST /api/seed/` - Seed database with sample tools

## Admin Panel

Access at: `http://localhost:8000/admin/`

## Migration from Supabase

### Data Export from Supabase

```bash
# Export data from Supabase
pg_dump -h db.xxx.supabase.co -U postgres -d postgres -t tools -t reviews -t deals -t news > supabase_data.sql

# Import to local PostgreSQL
psql one9founders < supabase_data.sql
```

### Update Frontend

Replace Supabase client calls with Django API calls:

**Before (Supabase):**
```typescript
const { data } = await supabase.from('tools').select('*');
```

**After (Django):**
```typescript
const response = await fetch('http://localhost:8000/api/tools/');
const data = await response.json();
```

## Environment Variables

Required environment variables:

```
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_NAME=one9founders
DATABASE_USER=your_db_user
DATABASE_PASSWORD=your_db_password
DATABASE_HOST=localhost
DATABASE_PORT=5432
GEMINI_API_KEY=your_gemini_key
FRONTEND_URL=http://localhost:3000
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

## Features Implemented

✅ PostgreSQL with pgvector for semantic search
✅ Google Gemini integration for embeddings
✅ REST API with Django REST Framework
✅ Google OAuth authentication
✅ CORS configuration for Next.js frontend
✅ Admin panel for content management
✅ All Supabase tables migrated
✅ Vector similarity search
✅ Newsletter subscriptions
✅ Tool submissions
✅ Reviews and ratings
✅ Deals management
✅ News articles

## Next Steps

1. Update frontend API calls to point to Django backend
2. Migrate existing Supabase data
3. Configure production database
4. Set up deployment (AWS, Heroku, etc.)
5. Configure email service for newsletters
# backend
# backend
