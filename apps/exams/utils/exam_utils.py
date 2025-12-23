# apps/exams/utils/exam_utils.py - UPDATED VERSION
from django.utils import timezone
from django.shortcuts import redirect
from django.contrib import messages

def can_access_exam(user, exam):
    """Check if user can access the exam"""
    # Admins can access everything
    if user.role == 'ADMIN':
        return True
    
    # Instructors can access their own exams
    if user.role == 'INSTRUCTOR' and exam.instructor == user:
        return True
    
    # Students can access if:
    # 1. They're enrolled in the course (if exam has a course)
    # 2. The exam is published
    if user.role == 'STUDENT':
        if not exam.is_published:
            return False
        
        if exam.course:
            # Check if student is enrolled in the course
            from apps.exams.models import Enrollment
            return Enrollment.objects.filter(
                student=user, 
                course=exam.course,
                is_active=True
            ).exists()
        else:
            # If no course assigned, allow access
            return True
    
    return False

def validate_exam_timing(exam, user):
    """Validate if exam can be taken based on timing"""
    now = timezone.now()
    
    # Check if exam has started
    if now < exam.start_date:
        return False, "Exam has not started yet."
    
    # Check if exam has ended
    if now > exam.end_date:
        return False, "Exam has ended."
    
    # Check if user has already submitted
    from apps.exams.models import Submission
    existing_submission = Submission.objects.filter(
        exam=exam,
        student=user
    ).first()
    
    if existing_submission and existing_submission.submitted_at:
        return False, "You have already submitted this exam."
    
    return True, ""

def prepare_exam_context(exam, user, submission=None):
    """Prepare context for exam taking page"""
    from apps.exams.models import Question, Answer
    
    questions = exam.questions.all().order_by('position')
    
    # Get existing answers if submission exists
    answers = {}
    if submission:
        for answer in submission.answers.all():
            answers[str(answer.question.question_id)] = answer
    
    return {
        'exam': exam,
        'questions': questions,
        'answers': answers,
        'submission': submission
    }

def calculate_time_remaining(submission, exam):
    """Calculate remaining time for an exam"""
    if not submission.started_at or submission.submitted_at:
        return 0
    
    if exam.time_limit_minutes:
        elapsed = timezone.now() - submission.started_at
        elapsed_minutes = elapsed.total_seconds() / 60
        remaining = exam.time_limit_minutes - elapsed_minutes
        return max(0, remaining)
    
    return None

def check_answer_plagiarism(answer, exam_id=None):
    """Run plagiarism check on an answer - moved to separate function"""
    # Import here to avoid circular imports
    from .plagiarism import BasicPlagiarismDetector
    detector = BasicPlagiarismDetector()
    return detector.check_answer(answer.answer_text, exam_id)