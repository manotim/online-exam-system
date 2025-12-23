# apps/proctoring/urls.py
from django.urls import path
from . import views

app_name = 'proctoring'

urlpatterns = [
    # Page views
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sessions/', views.session_list, name='session_list'),
    path('session/<uuid:session_id>/', views.session_detail, name='session_detail'),
    
    # API endpoints
    path('api/start_session/', views.start_proctoring_session, name='start_session'),
    path('api/log_activity/', views.log_suspicious_activity, name='log_activity'),
    path('api/take_screenshot/', views.take_screenshot, name='take_screenshot'),
    path('api/screenshot/<uuid:screenshot_id>/', views.get_screenshot, name='get_screenshot'),
    path('api/session/<uuid:session_id>/update/', views.update_session_status, name='update_session_status'),
]