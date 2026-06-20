from django.urls import path
from . import views

urlpatterns = [
    path('check-text/', views.check_text, name='check_text'),
]