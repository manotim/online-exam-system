# apps/analytics/models.py (create this file)
import uuid
from django.db import models
from apps.users.models import CustomUser
from apps.exams.models import Exam

class StudentPerformance(models.Model):
    performance_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    overall_score = models.DecimalField(max_digits=10, decimal_places=2)
    percentile = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    time_spent_minutes = models.IntegerField(null=True, blank=True)
    weak_areas = models.JSONField(default=list, blank=True)
    recommendations = models.TextField(blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'exam')
        verbose_name = 'Student Performance'
        verbose_name_plural = 'Student Performances'

    def __str__(self):
        return f"{self.student.email} - {self.exam.title}"


class ExamAnalytics(models.Model):
    analytics_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    total_students = models.IntegerField(default=0)
    average_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    highest_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lowest_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    question_analytics = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analytics for {self.exam.title}"