# apps/grading/urls.py - UPDATED WITH NEW VIEWS
from django.urls import path
from . import views

app_name = 'grading'

urlpatterns = [
    # Dashboard
    path('', views.grading_dashboard, name='dashboard'),
    # Add to apps/grading/urls.py
    path('start-session/', views.start_grading_session, name='start_session'),
    path('session/<uuid:session_id>/end/', views.end_grading_session, name='end_session'),
    path('simple-grade/<uuid:submission_id>/', views.simple_grade_submission, name='simple_grade'),
    path('bulk-grade/', views.bulk_grade_overview, name='bulk_grade'),  # For bulk grading overview
    
    # Submissions - NOTE: Fixed to match your view expectation
    path('submissions/', views.submissions_list, name='submissions_list'),
    path('submissions/exam/<uuid:exam_id>/', views.submissions_list, name='exam_submissions'),
    path('submissions/<uuid:submission_id>/grade/', views.grade_submission, name='grade_submission'),  # CHANGED to match your view
    
    # Bulk operations
    path('bulk/exam/<uuid:exam_id>/', views.bulk_grade, name='bulk_grade'),
    
    # Feedback
    path('feedback/<uuid:submission_id>/', views.view_feedback, name='view_feedback'),
    
    # NEW: Rubric management
    path('rubrics/', views.rubric_list, name='rubric_list'),
    path('rubrics/create/', views.create_rubric, name='create_rubric'),
    path('rubrics/<uuid:rubric_id>/', views.rubric_detail, name='rubric_detail'),
    
    # NEW: Analytics
    path('analytics/', views.grading_analytics, name='analytics'),
    path('analytics/exam/<uuid:exam_id>/', views.grading_analytics, name='exam_analytics'),
    
    # NEW: Grade publishing
    path('publish/exam/<uuid:exam_id>/', views.publish_grades, name='publish_grades'),
]