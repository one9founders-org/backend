from django.conf import settings
from django.db import models


# ── 1. CourseCategory ──────────────────────────────────────────────────
class CourseCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True, help_text="Icon class or emoji")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "education_course_categories"
        ordering = ["order", "name"]
        verbose_name_plural = "Course Categories"


# ── 2. AudienceType ───────────────────────────────────────────────────
class AudienceType(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)
    landing_page_url = models.URLField(blank=True)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "education_audience_types"
        ordering = ["order", "name"]
        verbose_name_plural = "Audience Types"


# ── 3. Instructor ─────────────────────────────────────────────────────
class Instructor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instructor_profile",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    title = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    short_bio = models.CharField(max_length=300, blank=True)
    photo = models.ImageField(upload_to="education/instructors/", blank=True)
    linkedin_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "education_instructors"
        ordering = ["name"]


# ── 4. Course ─────────────────────────────────────────────────────────
class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    FORMAT_CHOICES = [
        ("self_paced", "Self-Paced"),
        ("cohort", "Cohort-Based"),
        ("live", "Live"),
        ("hybrid", "Hybrid"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("coming_soon", "Coming Soon"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    # Basic
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    subtitle = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True, help_text="Supports markdown")
    short_description = models.CharField(max_length=300, blank=True)
    featured_image = models.URLField(blank=True)
    intro_video_url = models.URLField(blank=True)

    # Classification
    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
    )
    audiences = models.ManyToManyField(AudienceType, blank=True, related_name="courses")
    instructors = models.ManyToManyField(Instructor, blank=True, related_name="courses")
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="beginner",
        db_index=True,
    )
    format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default="self_paced",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )

    # Schedule
    duration_weeks = models.IntegerField(default=0)
    hours_per_week = models.IntegerField(default=0)
    total_lessons = models.IntegerField(default=0)
    next_cohort_date = models.DateField(null=True, blank=True)
    schedule_description = models.CharField(max_length=300, blank=True)

    # Content
    whats_included = models.JSONField(
        default=list, blank=True, help_text="List of strings"
    )
    tools_mentioned = models.JSONField(
        default=list, blank=True, help_text="List of tool slugs"
    )

    # Certificate
    certificate_description = models.CharField(
        max_length=500,
        default="Certificate issued through IIT Bombay Educational Outreach",
        blank=True,
    )
    has_certificate = models.BooleanField(default=True)

    # Language
    language = models.CharField(max_length=50, default="English")
    has_hindi_support = models.BooleanField(default=False)

    # External Links (iitb_eo_link NOT exposed in API)
    iitb_eo_link = models.URLField(
        blank=True, help_text="IIT Bombay EO link (internal only)"
    )

    # SEO
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    # Tracking
    is_featured = models.BooleanField(default=False, db_index=True)
    interest_count = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "education_courses"
        ordering = ["-is_featured", "-created_at"]


# ── 5. CourseModule ────────────────────────────────────────────────────
class CourseModule(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    duration_description = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    class Meta:
        db_table = "education_course_modules"
        ordering = ["order"]


# ── 6. CourseFAQ ──────────────────────────────────────────────────────
class CourseFAQ(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=500)
    answer = models.TextField()
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.course.title} - {self.question[:50]}"

    class Meta:
        db_table = "education_course_faqs"
        ordering = ["order"]
        verbose_name = "Course FAQ"
        verbose_name_plural = "Course FAQs"


# ── 7. Guide ──────────────────────────────────────────────────────────
class EducationGuide(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("review", "In Review"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    subtitle = models.CharField(max_length=300, blank=True)
    content = models.TextField(blank=True, help_text="Supports markdown")
    excerpt = models.CharField(max_length=500, blank=True)
    featured_image = models.URLField(blank=True)

    # Classification
    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guides",
    )
    author = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guides",
    )
    audiences = models.ManyToManyField(AudienceType, blank=True, related_name="guides")
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="beginner",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    read_time_minutes = models.IntegerField(default=0)
    tools_mentioned = models.JSONField(
        default=list, blank=True, help_text="List of tool slugs"
    )

    # Related
    related_course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_guides",
    )

    # SEO
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    # Tracking
    is_featured = models.BooleanField(default=False, db_index=True)
    view_count = models.IntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "education_guides"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Education Guide"
        verbose_name_plural = "Education Guides"


# ── 8. Workshop ───────────────────────────────────────────────────────
class EducationWorkshop(models.Model):
    FORMAT_CHOICES = [
        ("webinar", "Webinar"),
        ("workshop", "Workshop"),
        ("corporate", "Corporate"),
    ]
    STATUS_CHOICES = [
        ("upcoming", "Upcoming"),
        ("live", "Live"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=300, blank=True)

    # Schedule
    date = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=60)
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")

    # Classification
    format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default="webinar",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="upcoming",
        db_index=True,
    )
    platform = models.CharField(max_length=100, blank=True)
    meeting_link = models.URLField(
        blank=True, help_text="Internal only — not exposed in API"
    )
    recording_url = models.URLField(blank=True)

    # Relations
    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workshops",
    )
    instructor = models.ForeignKey(
        Instructor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workshops",
    )
    audiences = models.ManyToManyField(
        AudienceType, blank=True, related_name="workshops"
    )

    # Content
    max_participants = models.IntegerField(default=0)
    learning_outcomes = models.JSONField(
        default=list, blank=True, help_text="List of outcome strings"
    )
    prerequisites = models.TextField(blank=True)

    # Tracking
    registration_count = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "education_workshops"
        ordering = ["-date", "-created_at"]
        verbose_name = "Education Workshop"
        verbose_name_plural = "Education Workshops"


# ── 9. LearningPath + LearningPathModule ──────────────────────────────
class LearningPath(models.Model):
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=300, blank=True)
    icon = models.CharField(max_length=100, blank=True)
    audience = models.ForeignKey(
        AudienceType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_paths",
    )
    estimated_duration = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "education_learning_paths"
        ordering = ["order", "title"]


class LearningPathModule(models.Model):
    learning_path = models.ForeignKey(
        LearningPath, on_delete=models.CASCADE, related_name="modules"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    courses = models.ManyToManyField(
        Course, blank=True, related_name="learning_path_modules"
    )
    guides = models.ManyToManyField(
        EducationGuide, blank=True, related_name="learning_path_modules"
    )
    workshops = models.ManyToManyField(
        EducationWorkshop, blank=True, related_name="learning_path_modules"
    )

    def __str__(self):
        return f"{self.learning_path.title} - {self.title}"

    class Meta:
        db_table = "education_learning_path_modules"
        ordering = ["order"]


# ── 10. LandingPage ───────────────────────────────────────────────────
class LandingPage(models.Model):
    PAGE_TYPE_CHOICES = [
        ("students", "Students"),
        ("professionals", "Professionals"),
        ("entrepreneurs", "Entrepreneurs"),
        ("organizations", "Organizations"),
    ]

    page_type = models.CharField(max_length=30, choices=PAGE_TYPE_CHOICES, unique=True)

    # Hero
    hero_title = models.CharField(max_length=255)
    hero_subtitle = models.TextField(blank=True)
    hero_cta_text = models.CharField(max_length=100, blank=True)
    hero_cta_url = models.URLField(blank=True)
    hero_image = models.URLField(blank=True)

    # Pitch
    pitch_title = models.CharField(max_length=255, blank=True)
    pitch_content = models.TextField(blank=True, help_text="Supports markdown")

    # Flexible content
    content_blocks = models.JSONField(
        default=list,
        blank=True,
        help_text="Flexible content sections as JSON",
    )

    # Relations
    featured_courses = models.ManyToManyField(
        Course, blank=True, related_name="landing_pages"
    )

    # SEO
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Landing Page: {self.get_page_type_display()}"

    class Meta:
        db_table = "education_landing_pages"
        ordering = ["page_type"]


# ── 11. CourseInquiry (CRM) ────────────────────────────────────────────
class CourseInquiry(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("forwarded_to_iitb", "Forwarded to IITB"),
        ("enrolled", "Enrolled"),
        ("dropped", "Dropped"),
    ]

    # Related content (all optional)
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inquiries",
    )
    workshop = models.ForeignKey(
        EducationWorkshop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inquiries",
    )
    learning_path = models.ForeignKey(
        LearningPath,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inquiries",
    )

    # Source
    source_page = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL where form was submitted",
    )

    # Contact info
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    current_role = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)

    # Pipeline
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        db_index=True,
    )
    internal_notes = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.email}"

    class Meta:
        db_table = "education_course_inquiries"
        ordering = ["-created_at"]
        verbose_name = "Course Inquiry"
        verbose_name_plural = "Course Inquiries"


# ── 12. OrganizationInquiry ───────────────────────────────────────────
class OrganizationInquiry(models.Model):
    INQUIRY_TYPE_CHOICES = [
        ("college", "College"),
        ("corporate", "Corporate"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("proposal_sent", "Proposal Sent"),
        ("negotiating", "Negotiating"),
        ("won", "Won"),
        ("lost", "Lost"),
    ]

    inquiry_type = models.CharField(
        max_length=20, choices=INQUIRY_TYPE_CHOICES, db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        db_index=True,
    )

    # Contact
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    organization = models.CharField(max_length=255)
    role = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Details
    estimated_batch_size = models.IntegerField(default=0)
    preferred_timeline = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)

    # Pipeline
    internal_notes = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization} - {self.name}"

    class Meta:
        db_table = "education_organization_inquiries"
        ordering = ["-created_at"]
        verbose_name = "Organization Inquiry"
        verbose_name_plural = "Organization Inquiries"


# ── 13. WorkshopRegistration ──────────────────────────────────────────
class WorkshopRegistration(models.Model):
    workshop = models.ForeignKey(
        EducationWorkshop,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    organization = models.CharField(max_length=255, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} - {self.workshop.title}"

    class Meta:
        db_table = "education_workshop_registrations"
        ordering = ["-registered_at"]
        unique_together = ["email", "workshop"]
