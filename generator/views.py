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
from .agents import (
    BlogGenerationWorkflow, QuotaExceededError, InvalidApiKeyError,
    regenerate_content, download_yt_audio, transcribe_with_assemblyai
)
from .scoring import calculate_seo_score, calculate_readability_score, calculate_engagement_score
from .rag_service import process_pdf_and_store
from django.core.files.storage import default_storage
import uuid

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
            try:
                from .agents import groq_generate
                content = groq_generate(f"Write an attractive, well-structured blog post on the topic: {topic}. Use proper H2/H3 headings and write in Markdown.", max_tokens=1000)
                user = CustomUser.objects.get(username=request.user)
                blogPost = BlogPost.objects.create(
                    title=f"{topic}",
                    content=content,
                    author=user
                )
                return HttpResponse(json.dumps({'content': content, 'blogpost_id': blogPost.id}), content_type="application/json")
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
    """Legacy YouTube endpoint — now routes through the optimised single-call workflow."""
    if request.method == 'POST':
        data = json.loads(request.body)
        yt_link = data.get('yt_link', None)
        if not yt_link:
            return HttpResponse(json.dumps({'error': 'YouTube link is missing'}), status=400, content_type="application/json")

        video_id = get_youtube_video_id(yt_link)
        if not video_id:
            return HttpResponse(json.dumps({'error': 'Invalid YouTube URL'}), status=400, content_type="application/json")

        # Fetch transcript (no API call)
        try:
            ytt_api = YouTubeTranscriptApi()
            fetched = ytt_api.fetch(video_id)
            transcript_text = " ".join([snippet.text for snippet in fetched])
        except Exception as e:
            return HttpResponse(json.dumps({'error': f'Could not fetch transcript: {str(e)}'}), status=500, content_type="application/json")

        try:
            title = YouTube(yt_link).title
        except Exception:
            title = f"Blog from YouTube video"

        try:
            workflow = BlogGenerationWorkflow()
            result = workflow.run(transcript_text, {'tone': 'Informative', 'audience': 'General', 'target_length': 'Medium', 'language': 'English'})
            final_content = result['content']
            user = CustomUser.objects.get(username=request.user.username)
            blogPost = BlogPost.objects.create(title=title, content=final_content, author=user)
            return HttpResponse(json.dumps({'content': final_content, 'blogpost_id': blogPost.id}), content_type="application/json")
        except QuotaExceededError as e:
            return HttpResponse(json.dumps({'error': str(e), 'quota_exceeded': True}), status=429, content_type="application/json")
        except Exception as e:
            print(e)
            return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
    else:
        return HttpResponse(json.dumps({'error': 'Method not allowed'}), status=405, content_type="application/json")

@csrf_exempt
def generate_agent(request):
    if request.method == 'POST':
        try:
            # Parse parameters from multipart/form-data
            topic = request.POST.get('topic', '')
            tone = request.POST.get('tone', 'Informative')
            audience = request.POST.get('audience', 'General')
            target_length = request.POST.get('target_length', 'Medium')
            language = request.POST.get('language', 'English')
            use_search = request.POST.get('use_search', 'false') == 'true'
            input_type = request.POST.get('input_type', 'text') # text, yt, audio, rag
            yt_link = request.POST.get('yt_link', '')

            pdf_file = request.FILES.get('pdf_file')
            audio_file = request.FILES.get('audio_file')
            
            user = CustomUser.objects.get(username=request.user.username)
            use_rag = False

            # ----------------------------------------------------------------
            # Handle YouTube URL
            # Flow: yt-dlp (download audio) → AssemblyAI (transcribe) → Gemini (blog)
            # ----------------------------------------------------------------
            if input_type == 'yt' and yt_link:
                video_id = get_youtube_video_id(yt_link)
                if not video_id:
                    return HttpResponse(json.dumps({'error': 'Invalid YouTube URL'}), status=400, content_type="application/json")

                # Step 1: Download audio with yt-dlp
                try:
                    print(f"[YT] Downloading audio for video_id={video_id}...")
                    audio_path = download_yt_audio(yt_link, video_id)
                    print(f"[YT] Audio downloaded: {audio_path}")
                except Exception as dl_err:
                    return HttpResponse(
                        json.dumps({'error': f"Audio download failed: {str(dl_err)}"}),
                        status=500, content_type="application/json"
                    )

                # Step 2: Transcribe with AssemblyAI
                try:
                    transcript_text = transcribe_with_assemblyai(audio_path)
                except ValueError as ve:
                    return HttpResponse(
                        json.dumps({'error': str(ve)}),
                        status=500, content_type="application/json"
                    )
                except Exception as aai_err:
                    return HttpResponse(
                        json.dumps({'error': f"Transcription failed: {str(aai_err)}"}),
                        status=500, content_type="application/json"
                    )

                # Cap transcript length before passing to Gemini
                topic = transcript_text[:6000]


            # Handle RAG / PDF Document
            if input_type == 'rag' and pdf_file:
                from .models import Document
                filename = default_storage.save(f"documents/{pdf_file.name}", ContentFile(pdf_file.read()))
                file_path = default_storage.path(filename)
                
                doc = Document.objects.create(title=topic or pdf_file.name, file=filename, user=user)
                process_pdf_and_store(file_path, doc.id, user.id)
                use_rag = True
                if not topic: topic = f"Summary of {pdf_file.name}"
                
            # Handle Audio — transcription + blog are combined into one workflow call below.
            # We upload the file and obtain the transcript here (uses Files API, not counted
            # as a generative call on the free tier).
            if input_type == 'audio' and audio_file:
                try:
                    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
                    filename = default_storage.save(f"media/{audio_file.name}", ContentFile(audio_file.read()))
                    file_path = default_storage.path(filename)
                    audio_upload = genai.upload_file(path=file_path)
                    # Quick transcription — kept as a brief prompt to minimise token usage.
                    model = genai.GenerativeModel('gemini-2.0-flash')
                    trans_response = model.generate_content(
                        [audio_upload, "Transcribe this audio. Return ONLY the transcript text, no commentary."]
                    )
                    topic = trans_response.text.strip()[:6000]  # cap before blog generation
                except QuotaExceededError as e:
                    return HttpResponse(json.dumps({'error': str(e), 'quota_exceeded': True}), status=429, content_type="application/json")
                except Exception as e:
                    return HttpResponse(json.dumps({'error': f"Audio processing failed: {str(e)}"}), status=500, content_type="application/json")
                    
            if not topic:
                return HttpResponse(json.dumps({'error': 'Topic or input is missing'}), status=400, content_type="application/json")

            # Run Workflow
            params = {
                'tone': tone,
                'audience': audience,
                'target_length': target_length,
                'language': language,
                'use_search': use_search,
                'use_rag': use_rag
            }
            
            workflow = BlogGenerationWorkflow()
            result = workflow.run(topic, params)
            
            final_content = result['content']
            seo_data = result['seo_data']
            
            # Compute scores
            seo_score = calculate_seo_score(final_content, seo_data.get('meta_title'), seo_data.get('meta_description'), seo_data.get('keywords'))
            readability_score = calculate_readability_score(final_content)
            engagement_score = calculate_engagement_score(final_content)
            
            blogPost = BlogPost.objects.create(
                title=seo_data.get('meta_title', topic[:50]),
                content=final_content,
                author=user,
                tone=tone,
                audience=audience,
                target_length=target_length,
                language=language,
                meta_title=seo_data.get('meta_title'),
                meta_description=seo_data.get('meta_description'),
                keywords=seo_data.get('keywords'),
                seo_score=seo_score,
                readability_score=readability_score,
                engagement_score=engagement_score
            )

            # Save generated thumbnail image (if available)
            image_bytes = result.get('image_bytes')
            if image_bytes:
                try:
                    img_filename = f"thumbnails/blog_{blogPost.id}.png"
                    blogPost.thumbnail.save(img_filename, ContentFile(image_bytes), save=True)
                    print(f"[Image] Thumbnail saved: {img_filename}")
                except Exception as img_save_err:
                    print(f"[Image] Could not save thumbnail: {img_save_err}")

            # Initial Version
            from .models import BlogVersion
            BlogVersion.objects.create(
                post=blogPost,
                version_number=1,
                content=final_content
            )

            res_data = {
                'content': final_content, 
                'blogpost_id': blogPost.id,
                'seo_meta': seo_data,
                'scores': {
                    'seo': seo_score,
                    'readability': readability_score,
                    'engagement': engagement_score
                }
            }
            return HttpResponse(json.dumps(res_data), content_type="application/json")
        except InvalidApiKeyError as e:
            print(f"[APIKey] {e}")
            return HttpResponse(
                json.dumps({'error': str(e), 'invalid_api_key': True}),
                status=401, content_type="application/json"
            )
        except QuotaExceededError as e:
            print(f"[Quota] {e}")
            return HttpResponse(
                json.dumps({'error': str(e), 'quota_exceeded': True}),
                status=429, content_type="application/json"
            )
        except Exception as e:
            print(e)
            return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
    else:
        return HttpResponse(json.dumps({'error': 'Method not allowed'}), status=405, content_type="application/json")

@csrf_exempt
def regenerate_blog(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        blog_id = data.get('blog_id')
        instruction = data.get('instruction')
        
        if blog_id and instruction:
            try:
                blog = BlogPost.objects.get(id=blog_id, author=request.user)

                # Uses the shared regenerate_content helper — single API call, content capped.
                new_content = regenerate_content(blog.content, instruction)

                blog.content = new_content
                blog.save()

                # Save version
                from .models import BlogVersion
                latest_version = blog.versions.count()
                BlogVersion.objects.create(
                    post=blog,
                    version_number=latest_version + 1,
                    content=new_content
                )

                return HttpResponse(json.dumps({'status': 'success', 'content': new_content}), content_type="application/json")
            except QuotaExceededError as e:
                return HttpResponse(json.dumps({'error': str(e), 'quota_exceeded': True}), status=429, content_type="application/json")
            except Exception as e:
                return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
        else:
            return HttpResponse(json.dumps({'error': 'Missing parameters'}), status=400, content_type="application/json")
    return HttpResponse(json.dumps({'error': 'Method not allowed'}), status=405, content_type="application/json")
    
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
