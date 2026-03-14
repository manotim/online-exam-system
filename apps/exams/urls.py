# apps/exams/urls.py
from django.urls import path
from . import views
from . import views_plagiarism
from . import views_templates

app_name = 'exams'

urlpatterns = [
    path('', views.exam_list, name='exam_list'),
    path('create/', views.create_exam, name='create_exam'),
    path('<uuid:exam_id>/', views.exam_detail, name='exam_detail'),
    path('<uuid:exam_id>/take/', views.take_exam, name='take_exam'),
    # Plagiarism URLs
    path('plagiarism/', views_plagiarism.plagiarism_dashboard, name='plagiarism_dashboard'),
    path('plagiarism/check/<uuid:check_id>/', views_plagiarism.plagiarism_check_detail, name='plagiarism_check_detail'),
    path('answer/<uuid:answer_id>/check-plagiarism/', views_plagiarism.run_plagiarism_check, name='run_plagiarism_check'),
    path('exam/<uuid:exam_id>/bulk-plagiarism-check/', views_plagiarism.bulk_plagiarism_check, name='bulk_plagiarism_check'),

    # Template URLs
    path('templates/', views_templates.template_list, name='template_list'),
    path('templates/create/', views_templates.template_create, name='template_create'),
    path('templates/<uuid:template_id>/', views_templates.template_detail, name='template_detail'),
    path('templates/<uuid:template_id>/edit/', views_templates.template_edit, name='template_edit'),
    path('templates/<uuid:template_id>/delete/', views_templates.template_delete, name='template_delete'),
    path('templates/<uuid:template_id>/create-exam/', views_templates.template_create_exam, name='template_create_exam'),
    path('templates/<uuid:template_id>/add-question/', views_templates.template_add_question, name='template_add_question'),
    path('templates/question/<uuid:question_id>/delete/', views_templates.template_delete_question, name='template_delete_question'),
    # apps/exams/urls.py - add this line
    path('debug-submissions/', views.debug_submissions, name='debug_submissions'),
]