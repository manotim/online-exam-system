# apps/exams/admin.py
from django.contrib import admin
from .models import Course, Enrollment, Exam, Question, Submission, Answer

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'title', 'instructor', 'institution']
    list_filter = ['institution', 'instructor']
    search_fields = ['code', 'title', 'description']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'enrolled_at', 'is_active']
    list_filter = ['is_active', 'course']
    search_fields = ['student__email', 'course__code']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'instructor', 'start_date', 'end_date', 'is_published', 'total_points']
    list_filter = ['is_published', 'course', 'instructor']
    search_fields = ['title', 'description']
    readonly_fields = ['exam_id', 'created_at', 'updated_at']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'question_type', 'position', 'points', 'requires_manual_grading', 'rubric']
    list_filter = ['question_type', 'exam', 'requires_manual_grading']
    search_fields = ['question_text', 'exam__title']
    readonly_fields = ['question_id', 'created_at']
    
    # Make rubric field appear in admin
    autocomplete_fields = ['rubric']


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'submitted_at', 'total_score', 'is_graded', 'grading_status']
    list_filter = ['is_graded', 'grading_status', 'exam']
    search_fields = ['student__email', 'exam__title']
    readonly_fields = ['submission_id', 'created_at']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['submission', 'question', 'points_awarded', 'grader', 'graded_at']
    list_filter = ['grader', 'question__exam']
    search_fields = ['answer_text', 'submission__student__email']
    readonly_fields = ['answer_id', 'created_at']