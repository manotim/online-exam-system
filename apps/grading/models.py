# apps/grading/models.py
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
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