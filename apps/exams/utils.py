# apps/exams/utils.py - SIMPLIFIED VERSION
from django.utils import timezone
from django.contrib import messages
from .models import Enrollment, Submission

def can_access_exam(user, exam):
    """
    Check if a user can access an exam.
    Returns (can_access: bool, reason: str)
    """
    from django.utils import timezone
    from apps.exams.models import Enrollment
    
    print(f"CAN_ACCESS_DEBUG: Checking access for {user.email} ({user.role}) to exam '{exam.title}'")
    
    # Admin always has access
    if user.role == 'ADMIN':
        print("CAN_ACCESS_DEBUG: Admin access granted")
        return (True, "Administrator access")
    
    now = timezone.now()
    print(f"CAN_ACCESS_DEBUG: Current time: {now}")
    print(f"CAN_ACCESS_DEBUG: Exam start: {exam.start_date}, end: {exam.end_date}")
    
    # Check if exam is published (for students only)
    if user.role == 'STUDENT' and not exam.is_published:
        print("CAN_ACCESS_DEBUG: Student - exam not published")
        return (False, "This exam is not published yet.")
    
    # For instructors accessing their own exams
    if user.role == 'INSTRUCTOR' and exam.instructor == user:
        print("CAN_ACCESS_DEBUG: Instructor owns this exam")
        return (True, "Instructor access")
    
    # For instructors accessing other instructors' exams
    if user.role == 'INSTRUCTOR' and exam.instructor != user:
        print("CAN_ACCESS_DEBUG: Instructor doesn't own this exam")
        return (False, "This exam was created by another instructor.")
    
    # For students
    if user.role == 'STUDENT':
        print("CAN_ACCESS_DEBUG: Processing student access")
        # Check if enrolled in course (if exam has a course)
        if exam.course:
            print(f"CAN_ACCESS_DEBUG: Exam has course: {exam.course.code}")
            is_enrolled = Enrollment.objects.filter(
                student=user,
                course=exam.course,
                is_active=True
            ).exists()
            print(f"CAN_ACCESS_DEBUG: Student enrolled: {is_enrolled}")
            if not is_enrolled:
                return (False, "You are not enrolled in this course.")
        
        # Check time window
        if now < exam.start_date:
            print("CAN_ACCESS_DEBUG: Exam hasn't started yet")
            return (False, f"This exam starts at {exam.start_date.strftime('%Y-%m-%d %H:%M')}.")
        
        if now > exam.end_date:
            print("CAN_ACCESS_DEBUG: Exam has ended")
            # Students can view results after exam ends if they submitted
            submission_exists = exam.submissions.filter(
                student=user, 
                submitted_at__isnull=False
            ).exists()
            print(f"CAN_ACCESS_DEBUG: Student has submission: {submission_exists}")
            if submission_exists:
                return (True, "Viewing results of completed exam.")
            return (False, "This exam has ended.")
        
        print("CAN_ACCESS_DEBUG: Student access granted")
        return (True, "Access granted for active exam")
    
    # Default fallback
    print(f"CAN_ACCESS_DEBUG: Default fallback - no access")
    return (False, "No access permissions")


def calculate_time_remaining(exam, submission):
    """Calculate remaining time for an exam in minutes."""
    if not exam.time_limit_minutes or not submission.started_at:
        return None
    
    elapsed = (timezone.now() - submission.started_at).total_seconds() / 60
    remaining = exam.time_limit_minutes - elapsed
    
    return max(0, remaining)


def get_exam_status(exam, user=None):
    """
    Get the status of an exam for display purposes.
    Returns a dict with status information.
    """
    now = timezone.now()
    status = {
        'is_published': exam.is_published,
        'has_started': now >= exam.start_date,
        'has_ended': now > exam.end_date,
        'is_active': exam.start_date <= now <= exam.end_date,
        'is_upcoming': now < exam.start_date,
        'is_past': now > exam.end_date,
    }
    
    # Add user-specific status if user is provided
    if user:
        submission = Submission.objects.filter(exam=exam, student=user).first()
        if submission:
            status.update({
                'has_submission': True,
                'is_submitted': submission.submitted_at is not None,
                'is_graded': submission.is_graded,
                'submission': submission,
            })
    
    return status


def validate_exam_timing(exam, user):
    """
    Validate if a student can take the exam now.
    Returns (is_valid: bool, message: str)
    """
    if user.role != 'STUDENT':
        return True, "Non-student access"
    
    now = timezone.now()
    
    if not exam.is_published:
        return False, "This exam is not published yet."
    
    if now < exam.start_date:
        return False, f"Exam starts at {exam.start_date.strftime('%Y-%m-%d %H:%M')}"
    
    if now > exam.end_date:
        return False, "Exam has ended"
    
    # Check if student has already submitted
    submission = Submission.objects.filter(exam=exam, student=user).first()
    if submission and submission.submitted_at:
        return False, "You have already submitted this exam"
    
    return True, "Valid for taking"



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