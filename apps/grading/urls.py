# apps/grading/urls.py
from django.urls import path
from . import views

app_name = 'grading'

urlpatterns = [
    path('', views.grading_dashboard, name='dashboard'),
    path('submissions/', views.submissions_list, name='submissions_list'),
    path('submissions/<uuid:exam_id>/', views.submissions_list, name='submissions_list_exam'),
    path('submission/<uuid:submission_id>/', views.grade_submission, name='grade_submission'),
    path('submission/<uuid:submission_id>/simple/', views.simple_grade_submission, name='simple_grade_submission'),
    path('bulk/', views.bulk_grade_overview, name='bulk_overview'),  # Add this line
    path('bulk/<uuid:exam_id>/', views.bulk_grade, name='bulk_grade'),
    path('feedback/<uuid:submission_id>/', views.view_feedback, name='view_feedback'),
    path('publish/<uuid:exam_id>/', views.publish_grades, name='publish_grades'),
    path('analytics/', views.grading_analytics, name='analytics'),
    path('analytics/<uuid:exam_id>/', views.grading_analytics, name='exam_analytics'),
    path('rubrics/', views.rubric_list, name='rubric_list'),
    path('rubrics/create/', views.create_rubric, name='create_rubric'),
    path('rubrics/<uuid:rubric_id>/', views.rubric_detail, name='rubric_detail'),
    path('session/start/', views.start_grading_session, name='start_session'),
    path('session/<uuid:session_id>/end/', views.end_grading_session, name='end_session'),
]