# apps/grading/urls.py
from django.urls import path
from . import views

app_name = 'grading'

urlpatterns = [
    # Dashboard and main views
    path('', views.grading_dashboard, name='dashboard'),
    path('submissions/', views.submissions_list, name='submissions_list'),
    path('submissions/<uuid:exam_id>/', views.submissions_list, name='submissions_list_by_exam'),
    
    # Grading views
    path('submission/<uuid:submission_id>/', views.grade_submission, name='grade_submission'),
    path('submission/<uuid:submission_id>/simple/', views.simple_grade_submission, name='simple_grade_submission'),
    path('feedback/<uuid:submission_id>/', views.view_feedback, name='view_feedback'),
    
    # Submission flagging
    path('submission/<uuid:submission_id>/flag/', views.flag_submission, name='flag_submission'),
    path('flag/<uuid:flag_id>/', views.view_flag, name='view_flag'),
    
    # Bulk grading
    path('bulk/', views.bulk_grade_overview, name='bulk_overview'),
    path('bulk/<uuid:exam_id>/', views.bulk_grade, name='bulk_grade'),
    
    # Publishing
    path('publish/<uuid:exam_id>/', views.publish_grades, name='publish_grades'),
    
    # Analytics
    path('analytics/', views.grading_analytics, name='analytics'),
    path('analytics/<uuid:exam_id>/', views.grading_analytics, name='exam_analytics'),
    
    # Rubrics
    path('rubrics/', views.rubric_list, name='rubric_list'),
    path('rubrics/create/', views.create_rubric, name='create_rubric'),
    path('rubrics/<uuid:rubric_id>/', views.rubric_detail, name='rubric_detail'),
    
    # Grading sessions
    path('session/start/', views.start_grading_session, name='start_session'),
    path('session/<uuid:session_id>/end/', views.end_grading_session, name='end_session'),
]