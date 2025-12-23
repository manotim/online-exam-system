# apps/proctoring/admin.py
from django.contrib import admin
from .models import ProctoringSession, SuspiciousActivity, ProctoringScreenshot

@admin.register(ProctoringSession)
class ProctoringSessionAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam_title', 'start_time', 'status', 'tab_switch_count', 'screenshot_count')
    list_filter = ('status', 'start_time')
    search_fields = ('student__email', 'student__username', 'submission__exam__title')
    readonly_fields = ('session_id', 'start_time')
    
    def exam_title(self, obj):
        return obj.submission.exam.title if obj.submission and obj.submission.exam else 'N/A'
    exam_title.short_description = 'Exam'

@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    list_display = ('session', 'activity_type', 'timestamp', 'screenshot_taken')
    list_filter = ('activity_type', 'timestamp')
    search_fields = ('session__student__email', 'activity_type')
    readonly_fields = ('activity_id', 'timestamp')

@admin.register(ProctoringScreenshot)
class ProctoringScreenshotAdmin(admin.ModelAdmin):
    list_display = ('session', 'timestamp', 'reason', 'is_flagged')
    list_filter = ('is_flagged', 'timestamp', 'reason')
    search_fields = ('session__student__email', 'reason')
    readonly_fields = ('screenshot_id', 'timestamp')