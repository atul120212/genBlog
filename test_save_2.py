import os
import django
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GenBlog.settings')
django.setup()

from generator.models import CustomUser, BlogPost
from django.core.files.base import ContentFile
import urllib.request
import urllib.parse

def test_saving():
    with open('test_err.txt', 'w') as f:
        try:
            user = CustomUser.objects.first()
            if not user:
                print("No user.", file=f)
                return
            
            final_content = "Test content"
            
            # 1. Image gen
            prompt = "A blog header"
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=100&height=100&nologo=true"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                image_bytes = response.read()

            # 2. Db save
            blogPost = BlogPost.objects.create(
                title="test-title-2",
                content=final_content,
                author=user,
            )
            
            img_filename = f"thumbnails/blog_{blogPost.id}.png"
            blogPost.thumbnail.save(img_filename, ContentFile(image_bytes), save=True)
            print("Success", file=f)
            
        except Exception as e:
            traceback.print_exc(file=f)

if __name__ == "__main__":
    test_saving()
