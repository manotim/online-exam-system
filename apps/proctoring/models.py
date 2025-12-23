# apps/proctoring/models.py
import uuid
from django.db import models
from django.conf import settings

class ProctoringSession(models.Model):
    SESSION_STATUS = (
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('FLAGGED', 'Flagged'),
        ('REVIEWED', 'Reviewed'),
    )
    
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField('exams.Submission', on_delete=models.CASCADE, related_name='proctoring_session')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='ACTIVE')
    
    # Browser monitoring
    browser_name = models.CharField(max_length=100, blank=True)
    browser_version = models.CharField(max_length=50, blank=True)
    os_info = models.CharField(max_length=100, blank=True)
    screen_resolution = models.CharField(max_length=50, blank=True)
    
    # Security flags
    is_fullscreen = models.BooleanField(default=False)
    was_fullscreen_exit = models.BooleanField(default=False)
    tab_switch_count = models.IntegerField(default=0)
    focus_loss_count = models.IntegerField(default=0)
    copy_paste_attempts = models.IntegerField(default=0)
    right_click_attempts = models.IntegerField(default=0)
    
    # Screenshots
    screenshot_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'proctoring_sessions'
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Proctoring: {self.student.email} - {self.submission.exam.title}"

class SuspiciousActivity(models.Model):
    ACTIVITY_TYPES = (
        ('TAB_SWITCH', 'Tab Switch'),
        ('WINDOW_BLUR', 'Window Blur'),
        ('FULLSCREEN_EXIT', 'Fullscreen Exit'),
        ('COPY_PASTE', 'Copy/Paste Attempt'),
        ('RIGHT_CLICK', 'Right Click'),
        ('KEYBOARD_SHORTCUT', 'Keyboard Shortcut'),
        ('SCREENSHOT_FAILED', 'Screenshot Failed'),
    )
    
    activity_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSession, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
    screenshot_taken = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'suspicious_activities'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.activity_type} at {self.timestamp}"

class ProctoringScreenshot(models.Model):
    screenshot_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ProctoringSession, on_delete=models.CASCADE, related_name='screenshots')
    timestamp = models.DateTimeField(auto_now_add=True)
    image_path = models.CharField(max_length=500)  # Store path to image file
    reason = models.CharField(max_length=200)  # Why screenshot was taken
    is_flagged = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'proctoring_screenshots'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Screenshot: {self.session.student.email} - {self.timestamp}"