# apps/exams/models.py (CLEAN VERSION - No Grading Models)
import uuid
from django.db import models
from django.core.validators import MinValueValidator
from apps.users.models import CustomUser, Institution

# -------------------------------------------------------------
# 1. COURSE MODEL
# -------------------------------------------------------------

class Course(models.Model):
    course_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='courses_taught')
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.title}"


# -------------------------------------------------------------
# 2. ENROLLMENT MODEL
# -------------------------------------------------------------

class Enrollment(models.Model):
    enrollment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.email} -> {self.course.code}"


# -------------------------------------------------------------
# 3. EXAM MODEL
# -------------------------------------------------------------

class Exam(models.Model):
    exam_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='exams_created')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    time_limit_minutes = models.IntegerField(null=True, blank=True)
    total_points = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    passing_score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_published = models.BooleanField(default=False)
    require_secure_browser = models.BooleanField(default=False)
    enable_plagiarism_check = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


# -------------------------------------------------------------
# 4. QUESTION MODEL
# -------------------------------------------------------------

class Question(models.Model):
    QUESTION_TYPES = (
        ('MCQ', 'Multiple Choice'),
        ('TRUE_FALSE', 'True/False'),
        ('SHORT_ANSWER', 'Short Answer'),
        ('ESSAY', 'Essay'),
    )

    question_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    question_text = models.TextField()
    points = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    correct_answer = models.TextField(blank=True)
    options = models.JSONField(default=list, blank=True)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Grading-related fields - will reference grading app models
    rubric = models.ForeignKey('grading.Rubric', on_delete=models.SET_NULL, null=True, blank=True)
    requires_manual_grading = models.BooleanField(default=False)
    grading_instructions = models.TextField(blank=True)
    expected_answer_length = models.IntegerField(null=True, blank=True)  # Expected word count for essays

    def __str__(self):
        return f"{self.question_type}: {self.question_text[:50]}..."


# -------------------------------------------------------------
# 5. SUBMISSION MODEL
# -------------------------------------------------------------

class Submission(models.Model):
    GRADING_STATUS = (
        ('PENDING', 'Pending'),
        ('AUTO_GRADED', 'Auto-graded'),
        ('MANUALLY_GRADED', 'Manually Graded'),
        ('PARTIALLY_GRADED', 'Partially Graded'),
    )
    
    submission_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='submissions')
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_graded = models.BooleanField(default=False)
    grading_status = models.CharField(max_length=20, choices=GRADING_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('exam', 'student')

    def __str__(self):
        return f"{self.student.email} - {self.exam.title}"


# -------------------------------------------------------------
# 6. ANSWER MODEL
# -------------------------------------------------------------

class Answer(models.Model):
    answer_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    selected_options = models.JSONField(default=list, blank=True)
    points_awarded = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Grading-related fields
    grader = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='graded_answers'
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    rubric_scores = models.JSONField(default=dict, blank=True)  # Store rubric-based scores
    manual_feedback = models.TextField(blank=True)
    grading_notes = models.TextField(blank=True)  # Internal notes for grader

    def __str__(self):
        return f"Answer for Q{self.question.position}"
    


# apps/exams/models.py - Add these models at the end
class PlagiarismCheck(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    
    check_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey('Answer', on_delete=models.CASCADE, related_name='plagiarism_checks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    similarity_score = models.FloatField(null=True, blank=True)  # 0-1 scale
    sources_found = models.IntegerField(default=0)
    checked_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    report = models.JSONField(default=dict, blank=True)  # Detailed report
    
    class Meta:
        db_table = 'plagiarism_checks'
        ordering = ['-checked_at']
    
    def __str__(self):
        return f"Plagiarism Check: {self.answer} - {self.similarity_score or 'Pending'}"


# In your PlagiarismSource model, change:
class PlagiarismSource(models.Model):
    SOURCE_TYPES = (
        ('INTERNAL', 'Internal (from system)'),
        ('WEB', 'Web source'),
        ('DOCUMENT', 'Document upload'),
    )
    
    source_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # CHANGE THIS LINE:
    plagiarism_check = models.ForeignKey(PlagiarismCheck, on_delete=models.CASCADE, related_name='sources')
    # From: check = models.ForeignKey(PlagiarismCheck, ...
    # To:   plagiarism_check = models.ForeignKey(PlagiarismCheck, ...
    
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    similarity = models.FloatField()  # 0-1 scale
    source_text = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    source_name = models.CharField(max_length=500, blank=True)
    matched_text = models.TextField(blank=True)  # The matching portion
    
    class Meta:
        db_table = 'plagiarism_sources'
    
    def __str__(self):
        return f"Source: {self.source_type} - {self.similarity:.2f}"
    

# Add to apps/exams/models.py after existing models

class ExamTemplate(models.Model):
    """Template for creating exams with predefined structure"""
    template_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='exam_templates')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Template settings
    default_time_limit = models.IntegerField(null=True, blank=True, help_text="Default time limit in minutes")
    default_total_points = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    require_secure_browser = models.BooleanField(default=False)
    enable_plagiarism_check = models.BooleanField(default=False)
    
    # Metadata
    is_public = models.BooleanField(default=False, help_text="Share with other instructors")
    usage_count = models.IntegerField(default=0, help_text="Number of times used to create exams")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'exam_templates'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.instructor.email}"

class TemplateQuestion(models.Model):
    """Question in an exam template"""
    QUESTION_TYPES = (
        ('MCQ', 'Multiple Choice'),
        ('TRUE_FALSE', 'True/False'),
        ('SHORT_ANSWER', 'Short Answer'),
        ('ESSAY', 'Essay'),
    )
    
    template_question_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ExamTemplate, on_delete=models.CASCADE, related_name='template_questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    question_text = models.TextField()
    points = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # For MCQ questions
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.TextField(blank=True, help_text="For MCQ: correct option, For True/False: True/False")
    
    # For all questions
    instructions = models.TextField(blank=True)
    expected_answer_length = models.IntegerField(null=True, blank=True, help_text="Expected word count for essays")
    position = models.IntegerField(default=0)
    
    # Reference to rubric if needed
    rubric = models.ForeignKey('grading.Rubric', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'template_questions'
        ordering = ['position']
    
    def __str__(self):
        return f"{self.question_type}: {self.question_text[:50]}..."
    



