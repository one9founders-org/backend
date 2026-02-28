"""Data migration to seed the ChatGPT for Business guide."""

from django.db import migrations
from django.utils import timezone


GUIDE_CONTENT = """
<h2 id="what-is-chatgpt">1. What Is ChatGPT and Why Should You Care?</h2>

<p><a href="https://chat.openai.com" target="_blank" rel="noopener">ChatGPT</a> is an AI-powered conversational assistant built by OpenAI. It can draft emails, write marketing copy, brainstorm product ideas, analyse data, generate code, and much more &mdash; all through a simple chat interface.</p>

<p>For entrepreneurs and small-business owners in India, ChatGPT is a force multiplier. Instead of hiring separate specialists for copywriting, customer-support scripting, and market research, you can use ChatGPT to handle the first draft of all three &mdash; saving both time and money during the critical early stages of your venture.</p>

<p><strong>Key stats:</strong></p>
<ul>
  <li>100&nbsp;million+ weekly active users worldwide</li>
  <li>Available in 160+ countries, including India</li>
  <li>Free tier available &mdash; no credit card required to start</li>
</ul>

<h2 id="who-is-this-for">2. Who Is This Guide For?</h2>

<p>This guide is written for:</p>
<ul>
  <li><strong>First-time founders</strong> looking to automate repetitive tasks</li>
  <li><strong>Solo entrepreneurs</strong> who wear multiple hats and need quick, quality output</li>
  <li><strong>Small-business owners in India</strong> who want to explore AI without a steep learning curve</li>
  <li><strong>Non-technical professionals</strong> curious about how ChatGPT fits into daily business operations</li>
</ul>

<p>No coding knowledge is required. If you can type a message, you can use ChatGPT.</p>

<h2 id="getting-started">3. Getting Started</h2>

<h3>Step 1 &mdash; Create an Account</h3>
<ol>
  <li>Visit <a href="https://chat.openai.com" target="_blank" rel="noopener">chat.openai.com</a></li>
  <li>Click <strong>Sign Up</strong> and register with your email or Google account</li>
  <li>Verify your email and log in</li>
</ol>

<h3>Step 2 &mdash; Choose a Plan</h3>
<table>
  <thead>
    <tr><th>Plan</th><th>Price (approx.)</th><th>Best For</th></tr>
  </thead>
  <tbody>
    <tr><td>Free</td><td>$0</td><td>Trying out ChatGPT, light daily use</td></tr>
    <tr><td>Plus</td><td>$20/month</td><td>Faster responses, GPT-4o access, image generation</td></tr>
    <tr><td>Team</td><td>$25/user/month</td><td>Collaborative workspaces for small teams</td></tr>
    <tr><td>Enterprise</td><td>Custom</td><td>Advanced security, admin controls, unlimited usage</td></tr>
  </tbody>
</table>

<p><em>Tip: Start with the free plan. Upgrade to Plus only when you hit usage limits or need advanced features like image generation and file analysis.</em></p>

<h3>Step 3 &mdash; Write Your First Prompt</h3>
<p>Type a clear, specific instruction in the chat box. For example:</p>
<blockquote>
  <p>"Write a 100-word product description for a handmade leather wallet brand targeting young professionals in Mumbai."</p>
</blockquote>

<h2 id="core-features">4. Core Features Walkthrough</h2>

<h3>4.1 Conversational Chat</h3>
<p>Ask follow-up questions without repeating context. ChatGPT remembers the conversation thread, so you can iterate on ideas naturally.</p>

<h3>4.2 Custom Instructions</h3>
<p>Set a persistent persona. Go to <strong>Settings &rarr; Custom Instructions</strong> and tell ChatGPT about your business, tone of voice, and preferred output format. Every future response will respect these defaults.</p>

<h3>4.3 File Upload &amp; Analysis (Plus)</h3>
<p>Upload PDFs, spreadsheets, and images. ChatGPT can summarise reports, extract data from invoices, or describe product photos for your e-commerce listings.</p>

<h3>4.4 Image Generation with DALL-E (Plus)</h3>
<p>Generate social-media creatives, blog thumbnails, and ad visuals directly inside ChatGPT &mdash; no design tool needed.</p>

<h3>4.5 GPTs (Custom Bots)</h3>
<p>Build specialised mini-apps called GPTs for recurring tasks like &ldquo;Weekly Newsletter Drafter&rdquo; or &ldquo;Customer FAQ Bot.&rdquo; Share them with your team or publish them in the GPT Store.</p>

<h3>4.6 Web Browsing &amp; Plugins</h3>
<p>ChatGPT can search the web in real time, cite sources, and connect with third-party services for tasks like scheduling, CRM updates, and more.</p>

<h2 id="use-cases">5. Real-World Use Cases for Indian Entrepreneurs</h2>

<h3>Marketing &amp; Content</h3>
<ul>
  <li>Draft blog posts, social-media captions, and email campaigns in minutes</li>
  <li>Localise content for Hindi, Tamil, or regional audiences</li>
  <li>Generate SEO-friendly meta descriptions and title tags</li>
</ul>

<h3>Sales &amp; Customer Support</h3>
<ul>
  <li>Write cold-outreach emails that convert</li>
  <li>Create FAQ documents and chatbot scripts</li>
  <li>Summarise customer feedback to identify trends</li>
</ul>

<h3>Operations &amp; Strategy</h3>
<ul>
  <li>Analyse competitor websites and positioning</li>
  <li>Draft SOPs (Standard Operating Procedures) for your team</li>
  <li>Build financial models and forecast revenue scenarios</li>
</ul>

<h3>Product Development</h3>
<ul>
  <li>Brainstorm feature ideas and validate with pros/cons analysis</li>
  <li>Write user stories and acceptance criteria</li>
  <li>Generate boilerplate code for MVPs (Minimum Viable Products)</li>
</ul>

<p>Want to explore more AI tools for your startup? Check out our <a href="/services">services page</a> for personalised recommendations, or browse the <a href="/tool/chatgpt">ChatGPT listing in our AI tools directory</a> for reviews and alternatives.</p>

<h2 id="tips">6. Tips for Getting the Best Results</h2>

<ol>
  <li><strong>Be specific.</strong> Instead of &ldquo;Write a blog post,&rdquo; say &ldquo;Write a 600-word blog post about GST filing tips for freelancers in India.&rdquo;</li>
  <li><strong>Give context.</strong> Tell ChatGPT your industry, target audience, and desired tone.</li>
  <li><strong>Iterate.</strong> Treat the first response as a draft. Ask ChatGPT to &ldquo;make it shorter,&rdquo; &ldquo;add examples,&rdquo; or &ldquo;rewrite in a casual tone.&rdquo;</li>
  <li><strong>Use roles.</strong> Start with &ldquo;Act as a senior marketing strategist&rdquo; to unlock domain-specific language and frameworks.</li>
  <li><strong>Save reusable prompts.</strong> Keep a Notion doc or Google Sheet of your best prompts so you can reuse them quickly.</li>
  <li><strong>Combine with other tools.</strong> Pair ChatGPT with Canva for design, Notion for project management, or Zapier for automation.</li>
</ol>

<h2 id="common-mistakes">7. Common Mistakes to Avoid</h2>

<ul>
  <li><strong>Publishing AI output without editing.</strong> Always review and fact-check before publishing. ChatGPT can hallucinate statistics or outdated information.</li>
  <li><strong>Vague prompts.</strong> &ldquo;Help me with marketing&rdquo; will give you generic advice. Be precise about what you need.</li>
  <li><strong>Ignoring data privacy.</strong> Never paste sensitive customer data, passwords, or financial secrets into ChatGPT.</li>
  <li><strong>Over-relying on one tool.</strong> ChatGPT is powerful but not infallible. Cross-reference critical business decisions with domain experts.</li>
  <li><strong>Skipping Custom Instructions.</strong> Setting up your business context once saves you from repeating it in every conversation.</li>
</ul>

<h2 id="alternatives">8. Alternatives to ChatGPT</h2>

<p>While ChatGPT is the market leader, consider these alternatives based on your needs:</p>

<table>
  <thead>
    <tr><th>Tool</th><th>Best For</th><th>Pricing</th></tr>
  </thead>
  <tbody>
    <tr><td>Google Gemini</td><td>Deep Google Workspace integration</td><td>Free / $20 mo</td></tr>
    <tr><td>Claude (Anthropic)</td><td>Long-document analysis, safety-focused</td><td>Free / $20 mo</td></tr>
    <tr><td>Microsoft Copilot</td><td>Office 365 users, enterprise workflows</td><td>Free / $30 mo</td></tr>
    <tr><td>Perplexity AI</td><td>Research &amp; cited answers</td><td>Free / $20 mo</td></tr>
    <tr><td>Jasper</td><td>Marketing-specific AI content</td><td>From $49 mo</td></tr>
  </tbody>
</table>

<p>Explore all of these and 2,500+ more tools in our <a href="/tool/chatgpt">AI tools directory</a>.</p>

<h2 id="verdict">9. Verdict</h2>

<p>ChatGPT is the single most versatile AI tool available to entrepreneurs today. Whether you are drafting investor decks in Bengaluru, writing WhatsApp marketing copy in Delhi, or building an MVP in Hyderabad, ChatGPT can save you hours every week.</p>

<p><strong>Our recommendation:</strong> Start with the free plan, experiment with 3&ndash;5 use cases relevant to your business, and upgrade to Plus once you see measurable time savings. The ROI is almost immediate for most founders.</p>

<p><strong>Rating: 4.8 / 5</strong> &mdash; Best for entrepreneurs who need an all-in-one AI assistant without a steep learning curve.</p>

<p>Ready to explore more? Visit our <a href="/services">services page</a> for hands-on guidance, or discover the <a href="/tool/chatgpt">full ChatGPT review and alternatives</a> in our directory.</p>
"""


def seed_guide(apps, schema_editor):
    Guide = apps.get_model("api", "Guide")
    Tool = apps.get_model("api", "Tool")

    now = timezone.now()

    guide, created = Guide.objects.get_or_create(
        slug="chatgpt-for-business-india",
        defaults={
            "title": "How to Use ChatGPT for Business: A Practical Guide",
            "slug": "chatgpt-for-business-india",
            "short_description": (
                "A beginner-friendly, step-by-step guide to using ChatGPT for "
                "marketing, sales, operations, and product development in your startup."
            ),
            "content": GUIDE_CONTENT.strip(),
            "author": "One9Founders",
            "difficulty": "beginner",
            "estimated_time": "20 min",
            "category": "ai-fundamentals",
            "audience": "founders",
            "pricing": "free",
            "meta_title": "ChatGPT for Business India | Practical Guide 2026",
            "meta_description": (
                "Learn how to use ChatGPT for your business in India. "
                "Step-by-step guide covering marketing, sales, operations "
                "and product development for entrepreneurs."
            ),
            "is_published": True,
            "is_featured": True,
            "published_at": now,
            "last_updated": now,
        },
    )

    if created:
        # Link the ChatGPT tool if it exists
        chatgpt_tool = Tool.objects.filter(slug="chatgpt").first()
        if not chatgpt_tool:
            chatgpt_tool = Tool.objects.filter(name__iexact="ChatGPT").first()
        if chatgpt_tool:
            guide.tools_used.add(chatgpt_tool)


def remove_guide(apps, schema_editor):
    Guide = apps.get_model("api", "Guide")
    Guide.objects.filter(slug="chatgpt-for-business-india").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_guide_lab_workshop"),
    ]

    operations = [
        migrations.RunPython(seed_guide, remove_guide),
    ]
