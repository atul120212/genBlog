from django.urls import path
from .views import *

urlpatterns = [
    path('',index , name='index'),
    path('generate',generate,name='generate'),
    path('login',user_login , name='login'),
    path('register',register , name='register'),
    path('logout', user_logout, name='logout'),
    path('topic_view', topic_view, name='gemini'),
    path('yt_view', yt_view, name='gemini'),
    path('blog_submit', blog_submit, name='blog_submit'),
    path('explore', explore, name='explore'),
    path('blog/<slug:slug>', blog_detail, name='blog_detail'),
    path('blogs', user_blogs, name='user_blogs'),
    path('profile', profile, name='profile'),
    path('profile/<int:id>/', profileByID, name='profileByID'),
    path('like/<int:post_id>/', like_blog_post, name='like_blog_post'),
    path('blog/delete/<int:id>/', delete_blog, name='delete_blog'),
    path('blog/update/<int:id>/', update_blog, name='update_blog'),
    path('about', about, name='about'),
    path('contact', contact, name='contact'),
]