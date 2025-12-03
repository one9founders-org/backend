# 🚀 Quick Start Guide - One9Founders Django Backend

## ✅ Setup Complete!

Your Django backend is fully configured and ready to use.

### 📊 Database Info
- **Database**: `one9data`
- **User**: `one9user`
- **Password**: `12345678`
- **Host**: `localhost`
- **Port**: `5432`
- **pgvector**: ✅ Installed (v0.7.4)

### 👤 Admin Credentials
- **Username**: `admin`
- **Email**: `admin@one9founders.com`
- **Password**: `admin123`

### 📦 Seeded Data
- ✅ 8 Categories
- ✅ 5 Sample Tools
- ✅ 2 Sample Deals
- ✅ 2 News Articles

---

## 🏃 Running the Server

```bash
cd /Volumes/Asta/one9founders/backend
source venv/bin/activate
python manage.py runserver
```

Server will be available at: **http://localhost:8000**

---

## 🔗 API Endpoints

### Tools
```bash
# List all tools
GET http://localhost:8000/api/tools/

# Get single tool
GET http://localhost:8000/api/tools/1/

# Search tools (semantic search with pgvector)
POST http://localhost:8000/api/tools/search/
Content-Type: application/json
{
  "query": "AI writing assistant"
}

# Add new tool
POST http://localhost:8000/api/tools/
Content-Type: application/json
{
  "name": "Tool Name",
  "description": "Tool description",
  "category": "AI",
  "url": "https://example.com",
  "pricing_model": "Freemium",
  "pricing_from": 10,
  "billing_frequency": "Monthly"
}
```

### Reviews
```bash
# Get reviews for a tool
GET http://localhost:8000/api/reviews/?tool_id=1

# Add review
POST http://localhost:8000/api/reviews/
Content-Type: application/json
{
  "tool_id": 1,
  "user_name": "John Doe",
  "rating": 5,
  "title": "Great tool!",
  "comment": "Very helpful for my work"
}
```

### Deals
```bash
# List all deals
GET http://localhost:8000/api/deals/
```

### News
```bash
# List all news
GET http://localhost:8000/api/news/

# Get single news article
GET http://localhost:8000/api/news/1/
```

### Newsletter
```bash
# Subscribe to newsletter
POST http://localhost:8000/api/newsletter/subscribe/
Content-Type: application/json
{
  "email": "user@example.com",
  "source": "homepage"
}
```

### Categories
```bash
# List all categories
GET http://localhost:8000/api/categories/
```

---

## 🎨 Admin Panel

Access the admin panel at: **http://localhost:8000/admin/**

Login with:
- Username: `admin`
- Password: `admin123`

You can manage:
- Tools
- Categories
- Reviews
- Deals
- News Articles
- Newsletter Subscriptions
- User Accounts

---

## 🧪 Testing the API

### Using curl:

```bash
# Test tools endpoint
curl http://localhost:8000/api/tools/

# Test search
curl -X POST http://localhost:8000/api/tools/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "AI assistant"}'

# Test deals
curl http://localhost:8000/api/deals/
```

### Using Python:

```python
import requests

# Get all tools
response = requests.get('http://localhost:8000/api/tools/')
tools = response.json()
print(f"Found {len(tools)} tools")

# Search tools
response = requests.post(
    'http://localhost:8000/api/tools/search/',
    json={'query': 'AI writing assistant'}
)
results = response.json()
print(f"Search found {len(results)} results")
```

---

## 🔧 Common Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run server
python manage.py runserver

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run Django shell
python manage.py shell

# Seed more data
python seed_data.py
```

---

## 📝 Environment Variables

Update `.env` file with your credentials:

```env
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_NAME=one9data
DATABASE_USER=one9user
DATABASE_PASSWORD=12345678
DATABASE_HOST=localhost
DATABASE_PORT=5432
GEMINI_API_KEY=your_gemini_api_key
FRONTEND_URL=http://localhost:3000
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

---

## 🔄 Migrating Data from Supabase

### Export from Supabase:

```bash
# Export specific tables
pg_dump -h db.xxx.supabase.co -U postgres -d postgres \
  -t tools -t reviews -t deals -t news \
  --data-only --column-inserts > supabase_data.sql
```

### Import to Django:

```bash
# Import data
psql one9data < supabase_data.sql

# Or use Django management command
python manage.py loaddata supabase_data.json
```

---

## 🌐 Connecting Frontend

Update your Next.js frontend to use Django API:

### Before (Supabase):
```typescript
import { supabase } from '@/lib/supabaseClient';

const { data } = await supabase.from('tools').select('*');
```

### After (Django):
```typescript
const response = await fetch('http://localhost:8000/api/tools/');
const data = await response.json();
```

### Search Example:
```typescript
const response = await fetch('http://localhost:8000/api/tools/search/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: searchQuery })
});
const results = await response.json();
```

---

## 🎯 Next Steps

1. ✅ Backend is running
2. ⬜ Update frontend API calls
3. ⬜ Add your Gemini API key to `.env`
4. ⬜ Configure Google OAuth (optional)
5. ⬜ Deploy to production

---

## 🐛 Troubleshooting

### Server won't start:
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process if needed
kill -9 <PID>
```

### Database connection error:
```bash
# Check PostgreSQL is running
brew services list

# Restart PostgreSQL
brew services restart postgresql@14
```

### pgvector not working:
```bash
# Verify extension
psql one9data -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

---

## 📚 Documentation

- Django: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- pgvector: https://github.com/pgvector/pgvector
- Google Gemini: https://ai.google.dev/

---

## 🎉 Success!

Your Django backend is fully migrated from Supabase and ready to use!

Run the server and start building! 🚀
