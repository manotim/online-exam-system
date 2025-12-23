# apps/grading/admin.py
from django.contrib import admin
from .models import Rubric, RubricCriterion, GradingComment, GradingSession, GradeDistribution

@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ['name', 'rubric_type', 'instructor', 'max_score', 'is_public', 'is_active', 'created_at']
    list_filter = ['rubric_type', 'instructor', 'is_public', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['rubric_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    # Inline for criteria
    class RubricCriterionInline(admin.TabularInline):
        model = RubricCriterion
        extra = 1
        ordering = ['order']
    
    inlines = [RubricCriterionInline]


@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ['rubric', 'title', 'max_score', 'weight', 'order']
    list_filter = ['rubric']
    search_fields = ['title', 'description']
    ordering = ['rubric', 'order']
    readonly_fields = ['criterion_id']


@admin.register(GradingComment)
class GradingCommentAdmin(admin.ModelAdmin):
    list_display = ['text_preview', 'instructor', 'comment_type', 'category', 'usage_count', 'created_at']
    list_filter = ['comment_type', 'category', 'instructor', 'is_public']
    search_fields = ['text', 'category']
    readonly_fields = ['comment_id', 'created_at']
    ordering = ['-usage_count', '-created_at']
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Comment'


@admin.register(GradingSession)
class GradingSessionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'instructor', 'start_time', 'end_time', 'status', 'submissions_graded']
    list_filter = ['status', 'instructor', 'exam']
    search_fields = ['exam__title', 'instructor__email', 'notes']
    readonly_fields = ['session_id', 'start_time']
    ordering = ['-start_time']


@admin.register(GradeDistribution)
class GradeDistributionAdmin(admin.ModelAdmin):
    list_display = ['exam', 'question_preview', 'average_score', 'median_score', 'calculated_at']
    list_filter = ['exam']
    search_fields = ['exam__title']
    readonly_fields = ['distribution_id', 'calculated_at']
    
    def question_preview(self, obj):
        if obj.question:
            return f"Q{obj.question.position}: {obj.question.question_text[:30]}..."
        return "Overall Exam"
    question_preview.short_description = 'Question'