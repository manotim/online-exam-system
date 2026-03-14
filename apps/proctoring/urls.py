# apps/proctoring/urls.py
from django.urls import path
from . import views

app_name = 'proctoring'

urlpatterns = [
    # Core views
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sessions/', views.session_list, name='session_list'),
    path('session/<uuid:session_id>/', views.session_detail, name='session_detail'),
    
    # API endpoints
    path('api/start_session/', views.start_proctoring_session, name='start_session'),
    path('api/log_activity/', views.log_suspicious_activity, name='log_activity'),
    path('api/take_screenshot/', views.take_screenshot, name='take_screenshot'),
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),
    path('api/screenshot/<uuid:screenshot_id>/', views.get_screenshot, name='get_screenshot'),
    
    # NEW: Session management endpoints
    path('api/session/<uuid:session_id>/status/', views.update_session_status, name='update_status'),
    path('api/session/<uuid:session_id>/invalidate/', views.invalidate_exam, name='invalidate_exam'),
    
    # NEW: Review endpoints
    path('review/', views.review_dashboard, name='review_dashboard'),
    path('session/<uuid:session_id>/add_notes/', views.add_report_notes, name='add_report_notes'),
]