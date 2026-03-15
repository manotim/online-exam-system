# apps/grading/models.py
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.users.models import CustomUser
from apps.exams.models import Exam, Question

# -------------------------------------------------------------
# 1. RUBRIC MODELS
# -------------------------------------------------------------

class Rubric(models.Model):
    RUBRIC_TYPES = (
        ('ANALYTIC', 'Analytic Rubric'),
        ('HOLISTIC', 'Holistic Rubric'),
        ('CHECKLIST', 'Checklist Rubric'),
    )
    
    rubric_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    rubric_type = models.CharField(max_length=20, choices=RUBRIC_TYPES, default='ANALYTIC')
    max_score = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='rubrics')
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Grading Rubric'
        verbose_name_plural = 'Grading Rubrics'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_rubric_type_display()})"


class RubricCriterion(models.Model):
    criterion_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name='criteria')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    order = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = 'Rubric Criterion'
        verbose_name_plural = 'Rubric Criteria'
        ordering = ['rubric', 'order']
        unique_together = ('rubric', 'order')
    
    def __str__(self):
        return f"{self.title} (max: {self.max_score})"


# -------------------------------------------------------------
# 2. GRADING SUPPORT MODELS
# -------------------------------------------------------------

class GradingComment(models.Model):
    COMMENT_TYPES = (
        ('PRAISE', 'Praise'),
        ('SUGGESTION', 'Suggestion'),
        ('CRITIQUE', 'Critique'),
        ('GENERAL', 'General'),
    )
    
    comment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='grading_comments')
    text = models.TextField()
    comment_type = models.CharField(max_length=20, choices=COMMENT_TYPES, default='GENERAL')
    category = models.CharField(max_length=100, blank=True)  # e.g., "Grammar", "Content", "Structure"
    is_public = models.BooleanField(default=False)
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Grading Comment'
        verbose_name_plural = 'Grading Comments'
        ordering = ['-usage_count', '-created_at']
    
    def __str__(self):
        return f"{self.comment_type}: {self.text[:50]}..."


class GradingSession(models.Model):
    SESSION_STATUS = (
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('PAUSED', 'Paused'),
    )
    
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='grading_sessions')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='grading_sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='IN_PROGRESS')
    submissions_graded = models.IntegerField(default=0)
    average_time_per_submission = models.IntegerField(null=True, blank=True)  # in seconds
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Grading Session'
        verbose_name_plural = 'Grading Sessions'
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Grading session for {self.exam.title} by {self.instructor.email}"


class GradeDistribution(models.Model):
    distribution_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='grade_distributions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, null=True, blank=True)
    scores = models.JSONField(default=list)  # List of scores for this question/exam
    average_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    median_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    standard_deviation = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Grade Distribution'
        verbose_name_plural = 'Grade Distributions'
        unique_together = ('exam', 'question')
    
    def __str__(self):
        if self.question:
            return f"Grade distribution for Q{self.question.position} in {self.exam.title}"
        return f"Grade distribution for {self.exam.title}"


# -------------------------------------------------------------
# 3. SUBMISSION FLAGGING MODELS
# -------------------------------------------------------------

class SubmissionFlag(models.Model):
    """
    Model for flagging submissions that need review or have issues.
    This allows for multiple flags per submission and tracks resolution.
    """
    FLAG_TYPES = (
        ('academic_integrity', 'Academic Integrity Concern'),
        ('technical_issue', 'Technical Issue'),
        ('grading_discrepancy', 'Grading Discrepancy'),
        ('missing_submission', 'Missing Submission'),
        ('late_submission', 'Late Submission'),
        ('special_accommodation', 'Special Accommodation Required'),
        ('other', 'Other'),
    )
    
    SEVERITY_LEVELS = (
        ('low', 'Low - Minor concern'),
        ('medium', 'Medium - Should be reviewed soon'),
        ('high', 'High - Urgent attention needed'),
        ('critical', 'Critical - Blocks grading process'),
    )
    
    FLAG_STATUS = (
        ('active', 'Active - Needs attention'),
        ('in_review', 'In Review'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    )
    
    flag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission_id = models.UUIDField()  # This references the submission from another app
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='submission_flags')
    flagged_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='created_flags')
    
    # Flag details
    flag_type = models.CharField(max_length=30, choices=FLAG_TYPES, default='other')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='medium')
    status = models.CharField(max_length=20, choices=FLAG_STATUS, default='active')
    
    # Description
    reason = models.TextField(help_text="Detailed reason for flagging this submission")
    additional_notes = models.TextField(blank=True, help_text="Additional context or observations")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Resolution details
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name='resolved_flags')
    resolution_notes = models.TextField(blank=True, help_text="Notes about how this flag was resolved")
    
    # Actions taken
    hold_grading = models.BooleanField(default=False, 
        help_text="Should grading be held until this flag is resolved?")
    notify_student = models.BooleanField(default=False,
        help_text="Has the student been notified about this flag?")
    notify_admin = models.BooleanField(default=False,
        help_text="Have administrators been notified about this flag?")
    
    class Meta:
        verbose_name = 'Submission Flag'
        verbose_name_plural = 'Submission Flags'
        ordering = ['-severity', '-created_at']
        indexes = [
            models.Index(fields=['submission_id']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Flag for submission {self.submission_id} - {self.get_flag_type_display()} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if self.status in ['resolved', 'dismissed'] and not self.resolved_at:
            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)


class FlagComment(models.Model):
    """
    Comments/discussion on a specific flag (for communication between graders and admins)
    """
    comment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(SubmissionFlag, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Flag Comment'
        verbose_name_plural = 'Flag Comments'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment on {self.flag} by {self.user.email}"


class FlagHistory(models.Model):
    """
    Track changes to flags for auditing purposes
    """
    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flag = models.ForeignKey(SubmissionFlag, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    changed_at = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=50)  # e.g., 'status_change', 'severity_change', 'note_added'
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Flag History'
        verbose_name_plural = 'Flag Histories'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.change_type} on {self.flag} at {self.changed_at}"


class BulkFlagOperation(models.Model):
    """
    For flagging multiple submissions at once (e.g., all submissions from a specific student or exam)
    """
    operation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    initiated_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True)
    flag_type = models.CharField(max_length=30, choices=SubmissionFlag.FLAG_TYPES)
    reason = models.TextField()
    submission_ids = models.JSONField(default=list)  # List of submission UUIDs that were flagged
    count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')  # pending, in_progress, completed, failed
    
    class Meta:
        verbose_name = 'Bulk Flag Operation'
        verbose_name_plural = 'Bulk Flag Operations'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Bulk flag operation by {self.initiated_by.email} - {self.count} submissions"