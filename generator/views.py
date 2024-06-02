from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout, get_user_model
from .models import CustomUser, BlogPost, Like, ContactMessage
import os
import google.generativeai as genai
from django.http import HttpResponse, JsonResponse
import json
from youtube_transcript_api import YouTubeTranscriptApi
import re
from pytube import YouTube
from django.core.files.base import ContentFile
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings

def index(request):
    if request.user.is_authenticated:
        blogs = BlogPost.objects.filter(is_published=True).exclude(author=request.user).order_by('-created_at')[:3]
    else:
        blogs = BlogPost.objects.filter(is_published=True).order_by('-created_at')[:3]
    return render(request, 'index.html', context={'blogs': blogs})

def explore(request):
    if request.user.is_authenticated:
        blogs = BlogPost.objects.filter(is_published=True).exclude(author=request.user).order_by('-created_at')
    else:
        blogs = BlogPost.objects.filter(is_published=True).order_by('-created_at')
    return render(request, 'explore.html', context={'blogs': blogs})

@login_required
def generate(request):
    return render(request,'generator.html')

def user_login(request):
    if request.method == 'POST':
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            if CustomUser.objects.filter(email=email).exists():
                user = authenticate(request, username=email, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('index')
                else:
                    error_message = "Incorrect password."
                    return render(request, 'login.html', {'error_message': error_message})
            else:
                error_message = "User does not exist."
                return render(request, 'login.html', {'error_message': error_message})
        except Exception as e:
            print("Error:", e)
            error_message = "An error occurred during login."
            return render(request, 'login.html', {'error_message': error_message})
    return render(request, 'login.html')

def register(request):
    if request.method == 'POST':
        name = request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            if CustomUser.objects.filter(email=email).exists():
                error_message = "Email already exists."
                return render(request, 'register.html', {'error_message': error_message})
            new_user = CustomUser.objects.create_user(username=email, email=email, password=password, name=name)
            # login(request, new_user)
            return redirect('login')
        except Exception as e:
            print("Error:", e)
            error_message = "An error occurred during registration."
            return render(request, 'register.html', {'error_message': error_message})
    return render(request, 'register.html')

def user_logout(request):
    logout(request)
    return redirect('index')

def topic_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        topic = data.get('topic', None)
        if topic:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            model = genai.GenerativeModel('gemini-pro')
            try:
                response = model.generate_content(f"Write an attractive blog on the topic: {topic}.")
                user = CustomUser.objects.get(username=request.user)
                blogPost = BlogPost.objects.create(
                    title=f"{topic}",
                    content=response.text,
                    author=user
                )
                return HttpResponse(json.dumps({'content': response.text,'blogpost_id':blogPost.id}), content_type="application/json")
            except Exception as e:
                print(e)
                return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
        else:
            return HttpResponse(json.dumps({'error': 'Topic is missing'}), status=400, content_type="application/json")
    else:
        return HttpResponse(json.dumps({'error': 'Method not allowed'}), status=405, content_type="application/json")

def blog_submit(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        blogID = data.get('blogID')
        action = data.get('action')
        visibility = int(data.get('visibility'))
        if action == 'submit':
            try:
                blog = BlogPost.objects.get(id=blogID)
                blog.is_published = True
                blog.is_public = bool(visibility)

                blog.save()
                return HttpResponse(json.dumps({'content':"success"}), content_type="application/json")
            except Exception as e:
                print(e)
                return HttpResponse(json.dumps({'error': e}), content_type="application/json")
        elif action == 'cancel':
            try:
                blog = BlogPost.objects.get(id=blogID)
                blog.delete()
                return HttpResponse(json.dumps({'content':"success"}), content_type="application/json")
            except Exception as e:
                print(e)
                return HttpResponse(json.dumps({'error': e}), content_type="application/json")
        return HttpResponse(json.dumps({'error': 'Method not allowed'}), content_type="application/json")
        
def blog_detail(request, slug):
    blog = get_object_or_404(BlogPost, slug=slug)
    liked = False
    if request.user.is_authenticated:
        liked = Like.objects.filter(user=request.user, post=blog).exists()
    return render(request, 'blog_detail.html', {'blog': blog, 'liked': liked})

def user_blogs(request):
    blogs = BlogPost.objects.filter(author=request.user)
    return render(request, 'user_blogs.html', {'blogs':blogs})

@login_required
def profile(request):
    if request.method == 'POST':
        user = request.user
        name = request.POST.get('name')
        profile_img = request.FILES.get('profile_img')
        user.name = name
        if profile_img:
            if user.profile_img:
                old_image_path = user.profile_img.path
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            user.profile_img = profile_img
        user.save()
        return render(request, 'profile.html', {'user': request.user})
    return render(request, 'profile.html', {'user': request.user})

def profileByID(request,id):
    profile = CustomUser.objects.get(id=id)
    return render(request,'profile.html',{'profile': profile})

def like_blog_post(request, post_id):
    if request.method == "POST":
        post = get_object_or_404(BlogPost, id=post_id)
        user = request.user
        if Like.objects.filter(user=user, post=post).exists():
            return JsonResponse({"error": "You have already liked this post"}, status=400)
        else:
            like = Like(user=user, post=post)
            like.save()
            post.likes += 1
            post.save()
            return JsonResponse({"likes": post.likes})
    return JsonResponse({"error": "Invalid request"}, status=400)

def get_youtube_video_id(url):
  pattern = r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/(?:watch\?v=)?([^#&?]+)"
  match = re.search(pattern, url)
  if match:
    return match.group(1)
  else:
    return None

def yt_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        yt_link = data.get('yt_link', None)
        if yt_link:
            video_id = get_youtube_video_id(yt_link)
            title = YouTube(yt_link).title
            print(title)
            if video_id:
                try:
                    extraction = YouTubeTranscriptApi.get_transcript(video_id, languages=['en','en-IN','hi'])
                    final_text = ""
                    for item in extraction:
                        final_text += item['text']
                    try:
                        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
                        model = genai.GenerativeModel('gemini-pro')
                        response = model.generate_content(f"Based on the following transcript from a YouTube video,write a comprehensive blog article, write it based on the transcript, but dont make it look like a youtube video, make it look like a proper blog article:{final_text}")
                        response_data = response.candidates[0].content.parts[0].text
                        user = CustomUser.objects.get(username=request.user.username)
                        blogPost = BlogPost.objects.create(
                            title=title,
                            content=response_data,
                            author=user
                        )
                        return HttpResponse(json.dumps({'content': response_data, 'blogpost_id': blogPost.id}), content_type="application/json")
                    except Exception as e:
                        print(e)
                        return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
                except Exception as e:
                    print(e)
                    return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
            else:
                return HttpResponse(json.dumps({'error': "Error in YouTube link"}), status=400, content_type="application/json")
    else:
        return HttpResponse(json.dumps({'error': 'Method not allowed'}), status=400, content_type="application/json")
    
def delete_blog(request,id):
    try:
        blog = get_object_or_404(BlogPost, id=id)
        blog.delete()
        return redirect('/blogs')
    except Exception as e:
        return HttpResponse(json.dumps({'error':"Invalid id"}), content_type="application/json")

def update_blog(request,id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            title = data.get('title')
            content = data.get('content')

            blog = get_object_or_404(BlogPost, id=id)
            blog.title = title
            blog.content = content
            blog.save()
            return JsonResponse({'status': 'success', 'message': 'Blog updated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

def about(request):
    return render(request, 'about_us.html')

def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        print(name,email,message)
        if name and email and message:
            try:
                contact_message = ContactMessage.objects.create(name=name,email=email,message=message)
                messages.success(request, 'Your message has been sent successfully!')
                return redirect('contact')
                # return JsonResponse({'status': 'success', 'message': 'Message sent and saved successfully'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'All fields are required'}, status=400)
    return render(request, 'contact_us.html')