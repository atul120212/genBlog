import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GenBlog.settings')
django.setup()

from generator.models import CustomUser, BlogPost
from generator.scoring import calculate_seo_score, calculate_readability_score, calculate_engagement_score
from django.core.files.base import ContentFile
import urllib.request
import urllib.parse
import json

def test_saving():
    user = CustomUser.objects.first()
    
    final_content = "Test content"
    seo_data = {"meta_title": "test", "meta_description": "test", "keywords": "test"}
    
    # 1. Image gen
    prompt = "A professional blog header image for an article titled: 'test'. Themes: test."
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true"

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        image_bytes = response.read()
        print(f"[Image] Thumbnail generated via Pollinations.ai ({len(image_bytes)} bytes)")

    # 2. Db save
    try:
        blogPost = BlogPost.objects.create(
            title="test-title",
            content=final_content,
            author=user,
            tone="Informative",
        )
        print("BlogPost created.")
        
        img_filename = f"thumbnails/blog_{blogPost.id}.png"
        blogPost.thumbnail.save(img_filename, ContentFile(image_bytes), save=True)
        print(f"[Image] Thumbnail saved: {img_filename}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_saving()
