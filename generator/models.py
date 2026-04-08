from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, null=True, blank=True)
    profile_img = models.ImageField(upload_to='profiles/', blank=True, null=True)

    def __str__(self):
        return self.username

class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    slug = models.SlugField(unique=True, blank=True)
    author = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True, null=True)
    likes = models.PositiveIntegerField(default=0)
    
    # Phase 1: New Blog parameters
    tone = models.CharField(max_length=50, blank=True, null=True)
    audience = models.CharField(max_length=50, blank=True, null=True)
    target_length = models.CharField(max_length=50, blank=True, null=True)
    language = models.CharField(max_length=50, default='English')
    
    # Phase 1: SEO fields
    meta_title = models.CharField(max_length=255, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)
    keywords = models.TextField(blank=True, null=True)

    # Phase 2: Content Scoring
    seo_score = models.IntegerField(default=0)
    readability_score = models.IntegerField(default=0)
    engagement_score = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class Like(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'post')

class ContactMessage(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"

class BlogVersion(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.post.title} - v{self.version_number}"

    class Meta:
        ordering = ['-version_number']

class Document(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.title