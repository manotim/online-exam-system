# apps/analytics/urls.py - UPDATED VERSION
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Main dashboard - routes based on role
    path('', views.analytics_dashboard, name='dashboard'),
    
    # Student analytics
    path('performance/', views.performance_dashboard, name='performance_dashboard'),
    path('student/', views.student_performance, name='student_performance'),
    path('student/<int:student_id>/', views.student_performance, name='student_performance_detail'),
    
    # Exam analytics
    path('exam/<uuid:exam_id>/results/', views.exam_results, name='exam_results'),
    path('exam/<uuid:exam_id>/analytics/', views.exam_analytics, name='exam_analytics'),
    
    # Course analytics
    path('course/<uuid:course_id>/', views.course_analytics, name='course_analytics'),
    
    # Instructor analytics
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    
    # Admin analytics
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    
    # Export reports
    path('export/<str:report_type>/<uuid:object_id>/<str:format>/', views.export_report, name='export_report'),
    path('export/<str:report_type>/<int:object_id>/<str:format>/', views.export_report, name='export_report_student'),
    
    # API endpoints (for AJAX/charts)
    path('api/exam/<uuid:exam_id>/stats/', views.api_exam_stats, name='api_exam_stats'),
    path('api/student/progress/', views.api_student_progress, name='api_student_progress'),
    path('api/student/<int:student_id>/progress/', views.api_student_progress, name='api_student_progress_detail'),
]