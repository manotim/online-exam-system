# apps/core/context_processors.py
from apps.proctoring.models import ProctoringSession
from apps.exams.models import Submission  # Change this line - import from exams, not grading

def notification_counts(request):
    if request.user.is_authenticated:
        if request.user.role in ['INSTRUCTOR', 'ADMIN']:
            # Count flagged proctoring sessions
            flagged_count = ProctoringSession.objects.filter(
                submission__exam__instructor=request.user,
                status='FLAGGED'
            ).count()
            
            # Count pending grading
            pending_count = Submission.objects.filter(
                exam__instructor=request.user,
                is_graded=False,
                submitted_at__isnull=False
            ).count()
            
            return {
                'flagged_sessions_count': flagged_count,
                'grading_pending_count': pending_count
            }
    return {}