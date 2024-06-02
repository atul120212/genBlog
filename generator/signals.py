from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import BlogPost
import requests
import os
from django.core.files.base import ContentFile
from PIL import Image
from io import BytesIO

def download_image(url):
    response = requests.get(url)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        return img
    else:
        return None

@receiver(post_save, sender=BlogPost)
def generate_thumbnail(sender, instance, created, **kwargs):
    if created and not instance.thumbnail:
        limewire_api_endpoint = "https://api.limewire.com/api/image/generation"
        payload = {
            "prompt": f"Thumbnail for blog on topic : {instance.title}",
            "aspect_ratio": "1:1"
        }
        headers = {
            "Content-Type": "application/json",
            "X-Api-Version": "v1",
            "Accept": "application/json",
            "Authorization": f"Bearer {os.environ.get('IMAGE_GEN_API_KEY')}"
        }
        response = requests.post(limewire_api_endpoint, json=payload, headers=headers)
        data = response.json()
        thumbnail_url = data['data'][0]['asset_url']
        if thumbnail_url:
            img = download_image(thumbnail_url)
            if img:
                buffer = BytesIO()
                img.save(buffer, format=img.format)
                instance.thumbnail.save(f'{instance.title}_thumbnail.{img.format.lower()}', ContentFile(buffer.getvalue()), save=False)
                instance.save()
