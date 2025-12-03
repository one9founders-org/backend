# 🔗 Frontend Integration Guide

## Replace Supabase with Django API

### Step 1: Create API Client

Create `src/lib/apiClient.ts` in your Next.js project:

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// Generic fetch wrapper
async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  
  if (!response.ok) {
    throw new Error(`API Error: ${response.statusText}`);
  }
  
  return response.json();
}

// Tools API
export const toolsAPI = {
  getAll: () => fetchAPI('/tools/'),
  
  getById: (id: number) => fetchAPI(`/tools/${id}/`),
  
  search: (query: string) => 
    fetchAPI('/tools/search/', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  
  create: (data: any) =>
    fetchAPI('/tools/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  update: (id: number, data: any) =>
    fetchAPI(`/tools/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  
  delete: (id: number) =>
    fetchAPI(`/tools/${id}/`, {
      method: 'DELETE',
    }),
};

// Reviews API
export const reviewsAPI = {
  getByToolId: (toolId: number) => 
    fetchAPI(`/reviews/?tool_id=${toolId}`),
  
  create: (data: any) =>
    fetchAPI('/reviews/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Deals API
export const dealsAPI = {
  getAll: () => fetchAPI('/deals/'),
};

// News API
export const newsAPI = {
  getAll: () => fetchAPI('/news/'),
  getById: (id: number) => fetchAPI(`/news/${id}/`),
};

// Newsletter API
export const newsletterAPI = {
  subscribe: (email: string, source: string = 'homepage') =>
    fetchAPI('/newsletter/subscribe/', {
      method: 'POST',
      body: JSON.stringify({ email, source }),
    }),
};

// Categories API
export const categoriesAPI = {
  getAll: () => fetchAPI('/categories/'),
};
```

---

### Step 2: Update Environment Variables

Add to `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

---

### Step 3: Update Existing Files

#### Update `src/app/actions.ts`:

**Before:**
```typescript
import { supabase } from '@/lib/supabaseClient';

export async function searchTools(query: string) {
  const { data } = await supabase.from('tools').select('*');
  return data;
}
```

**After:**
```typescript
import { toolsAPI } from '@/lib/apiClient';

export async function searchTools(query: string) {
  return await toolsAPI.search(query);
}

export async function getAllTools() {
  return await toolsAPI.getAll();
}

export async function getToolById(id: number) {
  return await toolsAPI.getById(id);
}
```

---

#### Update `src/app/reviews/actions.ts`:

**Before:**
```typescript
import { supabase } from '@/lib/supabaseClient';

export async function addReview(reviewData: any) {
  const { error } = await supabase.from('reviews').insert(reviewData);
  return { success: !error };
}
```

**After:**
```typescript
import { reviewsAPI } from '@/lib/apiClient';

export async function addReview(reviewData: any) {
  try {
    await reviewsAPI.create(reviewData);
    return { success: true };
  } catch (error) {
    return { success: false, error };
  }
}

export async function getReviewsForTool(toolId: number) {
  return await reviewsAPI.getByToolId(toolId);
}
```

---

#### Update Newsletter Subscription:

**Before:**
```typescript
const { error } = await supabase
  .from('newsletter_subscriptions')
  .insert({ email });
```

**After:**
```typescript
import { newsletterAPI } from '@/lib/apiClient';

try {
  await newsletterAPI.subscribe(email);
  // Success
} catch (error) {
  // Handle error
}
```

---

### Step 4: Update Components

#### Example: PortfolioSection Component

**Before:**
```typescript
'use client';
import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';

export default function PortfolioSection() {
  const [tools, setTools] = useState([]);
  
  useEffect(() => {
    async function fetchTools() {
      const { data } = await supabase.from('tools').select('*');
      setTools(data || []);
    }
    fetchTools();
  }, []);
  
  return (
    // ... render tools
  );
}
```

**After:**
```typescript
'use client';
import { useEffect, useState } from 'react';
import { toolsAPI } from '@/lib/apiClient';

export default function PortfolioSection() {
  const [tools, setTools] = useState([]);
  
  useEffect(() => {
    async function fetchTools() {
      const data = await toolsAPI.getAll();
      setTools(data || []);
    }
    fetchTools();
  }, []);
  
  return (
    // ... render tools
  );
}
```

---

### Step 5: Update Search Component

**Before:**
```typescript
const { data } = await supabase.rpc('match_tools', {
  query_embedding: embedding,
  match_threshold: 0.3,
  match_count: 10,
});
```

**After:**
```typescript
import { toolsAPI } from '@/lib/apiClient';

const results = await toolsAPI.search(query);
```

---

### Step 6: Remove Supabase Dependencies

```bash
# Remove Supabase package
npm uninstall @supabase/supabase-js

# Remove Supabase client file
rm src/lib/supabaseClient.ts
```

---

## 🔄 Migration Checklist

### Files to Update:
- [ ] `src/lib/apiClient.ts` - Create new API client
- [ ] `src/app/actions.ts` - Update tool actions
- [ ] `src/app/reviews/actions.ts` - Update review actions
- [ ] `src/components/PortfolioSection.tsx` - Update tools fetching
- [ ] `src/components/SearchInput.tsx` - Update search
- [ ] `src/components/NewsletterSignup.tsx` - Update subscription
- [ ] `src/components/ReviewForm.tsx` - Update review submission
- [ ] `src/app/deals/page.tsx` - Update deals fetching
- [ ] `src/app/news/page.tsx` - Update news fetching
- [ ] `.env.local` - Add API URL

### Remove:
- [ ] `src/lib/supabaseClient.ts`
- [ ] `@supabase/supabase-js` package
- [ ] Supabase environment variables

---

## 🧪 Testing

### Test Each Endpoint:

```typescript
// Test in browser console or create a test file

// 1. Test tools
const tools = await fetch('http://localhost:8000/api/tools/').then(r => r.json());
console.log('Tools:', tools);

// 2. Test search
const search = await fetch('http://localhost:8000/api/tools/search/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'AI assistant' })
}).then(r => r.json());
console.log('Search results:', search);

// 3. Test deals
const deals = await fetch('http://localhost:8000/api/deals/').then(r => r.json());
console.log('Deals:', deals);

// 4. Test newsletter
const newsletter = await fetch('http://localhost:8000/api/newsletter/subscribe/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'test@example.com', source: 'homepage' })
}).then(r => r.json());
console.log('Newsletter:', newsletter);
```

---

## 🚨 Common Issues

### CORS Errors
If you see CORS errors, make sure Django backend has:

```python
# config/settings.py
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
]
CORS_ALLOW_CREDENTIALS = True
```

### 404 Errors
Check that:
1. Django server is running: `python manage.py runserver`
2. API URL is correct in `.env.local`
3. Endpoint paths match Django URLs

### Authentication Issues
For authenticated requests, add token:

```typescript
const token = localStorage.getItem('authToken');

fetch(url, {
  headers: {
    'Authorization': `Token ${token}`,
    'Content-Type': 'application/json',
  }
})
```

---

## 📊 Response Format Differences

### Supabase Response:
```typescript
{
  data: [...],
  error: null
}
```

### Django Response:
```typescript
[...] // Direct array or object
```

Update your code to handle direct responses instead of `data` wrapper.

---

## 🎯 Quick Migration Script

Create `scripts/migrate-to-django.sh`:

```bash
#!/bin/bash

echo "🔄 Migrating from Supabase to Django..."

# 1. Create API client
cat > src/lib/apiClient.ts << 'EOF'
// API client code here
EOF

# 2. Update environment
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" >> .env.local

# 3. Remove Supabase
npm uninstall @supabase/supabase-js
rm src/lib/supabaseClient.ts

echo "✅ Migration setup complete!"
echo "📝 Now update your components to use the new API client"
```

---

## ✅ Verification

After migration, verify:

1. ✅ All pages load without errors
2. ✅ Search functionality works
3. ✅ Tools display correctly
4. ✅ Reviews can be submitted
5. ✅ Newsletter subscription works
6. ✅ Deals page loads
7. ✅ News articles display
8. ✅ No Supabase imports remain

---

## 🚀 Deploy

### Development:
```bash
# Terminal 1: Django backend
cd backend
source venv/bin/activate
python manage.py runserver

# Terminal 2: Next.js frontend
cd one9founders
npm run dev
```

### Production:
Update API URL in production:
```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api
```

---

## 📞 Quick Reference

**API Base URL**: `http://localhost:8000/api`  
**Tools**: `/api/tools/`  
**Search**: `/api/tools/search/` (POST)  
**Reviews**: `/api/reviews/`  
**Deals**: `/api/deals/`  
**News**: `/api/news/`  
**Newsletter**: `/api/newsletter/subscribe/` (POST)  

---

*Happy coding! 🎉*
