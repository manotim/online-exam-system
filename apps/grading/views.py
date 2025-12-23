# apps/grading/views.py - FULLY UPDATED VERSION
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from apps.exams.models import Exam, Submission, Answer
from apps.users.models import CustomUser
from apps.grading.models import Rubric, RubricCriterion, GradingSession  # NEW IMPORTS
from apps.grading.services import AutoGradingService, RubricGradingService, AnalyticsService, NotificationService  # NEW IMPORTS


# apps/grading/views.py - UPDATE THE grading_dashboard FUNCTION
@login_required
def grading_dashboard(request):
    """Dashboard for instructors to see submissions needing grading"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can access grading.')
        return redirect('core:dashboard')
    
    # Get exams created by this instructor
    exams = Exam.objects.filter(instructor=request.user, is_published=True)
    
    # Get submissions needing grading (for the table)
    pending_submissions = []
    for exam in exams:
        submissions = exam.submissions.filter(submitted_at__isnull=False, is_graded=False)
        for submission in submissions:
            # Check if any answers need manual grading
            needs_grading = submission.answers.filter(
                question__question_type__in=['SHORT_ANSWER', 'ESSAY'],
                points_awarded__isnull=True
            ).exists()
            
            if needs_grading:
                pending_submissions.append(submission)
    
    # Get total counts
    total_pending = len(pending_submissions)
    
    # Get graded submissions count
    graded_submissions = Submission.objects.filter(
        exam__in=exams,
        submitted_at__isnull=False,
        is_graded=True
    )
    total_graded = graded_submissions.count()
    
    # Get active grading session
    active_session = GradingSession.objects.filter(
        instructor=request.user,
        status='IN_PROGRESS'
    ).first()
    
    # Get recent grading activity (last 10 graded answers)
    recent_grading = Answer.objects.filter(
        grader=request.user,
        graded_at__isnull=False
    ).select_related('question', 'submission', 'submission__exam').order_by('-graded_at')[:10]
    
    context = {
        'active_session': active_session,
        'pending_submissions': pending_submissions[:15],  # Limit for dashboard table
        'recent_grading': recent_grading,
        'total_pending': total_pending,
        'total_graded': total_graded,
        'total_exams': exams.count(),
    }
    
    return render(request, 'grading/dashboard.html', context)





@login_required
def submissions_list(request, exam_id=None):
    """List all submissions for an exam or all exams"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can access submissions.')
        return redirect('core:dashboard')
    
    if exam_id:
        exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
        submissions = exam.submissions.filter(submitted_at__isnull=False).order_by('-submitted_at')
        exam_filter = exam
    else:
        exams = Exam.objects.filter(instructor=request.user, is_published=True)
        submissions = Submission.objects.filter(
            exam__in=exams,
            submitted_at__isnull=False
        ).order_by('-submitted_at')
        exam_filter = None
    
    # Filter by grading status
    grading_filter = request.GET.get('filter', 'all')
    if grading_filter == 'pending':
        submissions = submissions.filter(is_graded=False)
    elif grading_filter == 'graded':
        submissions = submissions.filter(is_graded=True)
    
    context = {
        'submissions': submissions,
        'exam_filter': exam_filter,
        'grading_filter': grading_filter,
        'total_count': submissions.count(),
    }
    
    return render(request, 'grading/submissions_list.html', context)


@login_required
def grade_submission(request, submission_id):
    """Grade a specific submission - UPDATED WITH SERVICES"""
    submission = get_object_or_404(Submission, submission_id=submission_id)
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can grade submissions.')
        return redirect('core:dashboard')
    
    if submission.exam.instructor != request.user:
        messages.error(request, 'You can only grade submissions for your own exams.')
        return redirect('grading:submissions_list')
    
    # Get or create grading session
    grading_session, created = GradingSession.objects.get_or_create(
        instructor=request.user,
        exam=submission.exam,
        status='IN_PROGRESS',
        defaults={'start_time': timezone.now()}
    )
    
    # Get answers that need manual grading
    answers_to_grade = submission.answers.filter(
        Q(question__question_type__in=['SHORT_ANSWER', 'ESSAY']) |
        Q(points_awarded__isnull=True)
    ).select_related('question').order_by('question__position')
    
    if request.method == 'POST':
        graded_answers = 0
        
        for answer in answers_to_grade:
            question = answer.question
            
            if question.rubric:
                # Rubric-based grading
                rubric_scores = {}
                for criterion in question.rubric.criteria.all():
                    score_key = f'criterion_{criterion.criterion_id}_{answer.answer_id}'
                    if score_key in request.POST:
                        try:
                            score = float(request.POST[score_key])
                            if 0 <= score <= criterion.max_score:
                                rubric_scores[str(criterion.criterion_id)] = score
                        except (ValueError, TypeError):
                            continue
                
                if rubric_scores:
                    feedback = request.POST.get(f'feedback_{answer.answer_id}', '')
                    RubricGradingService.apply_rubric_to_answer(
                        answer, rubric_scores, request.user, feedback
                    )
                    graded_answers += 1
            else:
                # Simple point-based grading
                points_key = f'points_{answer.answer_id}'
                feedback_key = f'feedback_{answer.answer_id}'
                
                if points_key in request.POST:
                    try:
                        points = float(request.POST[points_key])
                        max_points = answer.question.points
                        
                        if 0 <= points <= max_points:
                            answer.points_awarded = points
                            answer.manual_feedback = request.POST.get(feedback_key, '')
                            answer.grader = request.user
                            answer.graded_at = timezone.now()
                            answer.save()
                            graded_answers += 1
                    except (ValueError, TypeError):
                        continue
        
        # Update submission status using service
        if graded_answers > 0:
            AutoGradingService.update_submission_status(submission)
            
            # Update grading session
            grading_session.submissions_graded += 1
            grading_session.save()
            
            messages.success(request, f'Graded {graded_answers} answers.')
        else:
            messages.warning(request, 'No grades were saved.')
        
        return redirect('grading:grade_submission', submission_id=submission_id)
    
    context = {
        'submission': submission,
        'answers_to_grade': answers_to_grade,
        'student': submission.student,
        'exam': submission.exam,
        'grading_session': grading_session,
    }
    
    return render(request, 'grading/grade_submission.html', context)


@login_required
def bulk_grade(request, exam_id):
    """Bulk grading interface for an exam - UPDATED"""
    exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
    
    if request.method == 'POST':
        graded_count = 0
        
        # Handle bulk grading
        for key, value in request.POST.items():
            if key.startswith('points_'):
                parts = key.split('_')
                if len(parts) == 3:
                    answer_id = parts[2]
                    try:
                        answer = Answer.objects.get(
                            answer_id=answer_id,
                            submission__exam=exam
                        )
                        points = float(value)
                        if 0 <= points <= answer.question.points:
                            answer.points_awarded = points
                            answer.grader = request.user
                            answer.graded_at = timezone.now()
                            answer.save()
                            graded_count += 1
                    except (Answer.DoesNotExist, ValueError):
                        continue
        
        if graded_count > 0:
            # Update all submission statuses
            submissions = exam.submissions.filter(submitted_at__isnull=False)
            for submission in submissions:
                AutoGradingService.update_submission_status(submission)
            
            messages.success(request, f'Graded {graded_count} answers across all submissions.')
        else:
            messages.warning(request, 'No grades were saved.')
        
        return redirect('grading:bulk_grade', exam_id=exam_id)
    
    # Get all submissions for this exam
    submissions = exam.submissions.filter(submitted_at__isnull=False).order_by('student__email')
    
    # Get questions that need manual grading
    questions = exam.questions.filter(
        question_type__in=['SHORT_ANSWER', 'ESSAY']
    ).order_by('position')
    
    context = {
        'exam': exam,
        'submissions': submissions,
        'questions': questions,
    }
    
    return render(request, 'grading/bulk_grade.html', context)


@login_required
def view_feedback(request, submission_id):
    """View feedback for a submission (for students)"""
    submission = get_object_or_404(Submission, submission_id=submission_id)
    
    # Check permissions
    if request.user.role != 'STUDENT' or submission.student != request.user:
        if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
            messages.error(request, 'Access denied.')
            return redirect('core:dashboard')
    
    context = {
        'submission': submission,
        'exam': submission.exam,
        'answers': submission.answers.select_related('question').order_by('question__position'),
    }
    
    return render(request, 'grading/view_feedback.html', context)


# NEW VIEWS FOR WEEK 4 COMPLETION

@login_required
def publish_grades(request, exam_id):
    """Publish grades for an exam"""
    exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
    
    if request.method == 'POST':
        # Use NotificationService to publish grades
        result = NotificationService.bulk_publish_grades(exam)
        
        messages.success(request, f'Published grades for {result["total_published"]} submissions.')
        return redirect('grading:submissions_list', exam_id=exam_id)
    
    # Get submissions ready for publishing
    submissions = exam.submissions.filter(is_graded=True).order_by('student__email')
    
    context = {
        'exam': exam,
        'submissions': submissions,
        'total_graded': submissions.count(),
        'total_submissions': exam.submissions.count(),
    }
    
    return render(request, 'grading/publish_grades.html', context)


@login_required
def grading_analytics(request, exam_id=None):
    """View grading analytics"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can view analytics.')
        return redirect('core:dashboard')
    
    if exam_id:
        exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
        distributions = []
        
        # Calculate distribution for each question
        for question in exam.questions.all():
            distribution = AnalyticsService.calculate_grade_distribution(exam, question)
            if distribution:
                distributions.append(distribution)
        
        # Calculate overall exam distribution
        exam_distribution = AnalyticsService.calculate_grade_distribution(exam)
        
        context = {
            'exam': exam,
            'distributions': distributions,
            'exam_distribution': exam_distribution,
        }
        
        return render(request, 'grading/exam_analytics.html', context)
    else:
        # Overall analytics for instructor
        efficiency = AnalyticsService.get_grading_efficiency(request.user)
        
        context = {
            'efficiency': efficiency,
        }
        
        return render(request, 'grading/analytics_dashboard.html', context)


@login_required
def rubric_list(request):
    """List all rubrics created by the instructor"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can manage rubrics.')
        return redirect('core:dashboard')
    
    rubrics = Rubric.objects.filter(instructor=request.user).order_by('-created_at')
    
    context = {
        'rubrics': rubrics,
    }
    return render(request, 'grading/rubric_list.html', context)


@login_required
def create_rubric(request):
    """Create a new rubric"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can create rubrics.')
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        rubric_type = request.POST.get('rubric_type', 'ANALYTIC')
        description = request.POST.get('description', '')
        max_score = request.POST.get('max_score', 10)
        
        # Create rubric
        rubric = Rubric.objects.create(
            name=name,
            rubric_type=rubric_type,
            description=description,
            max_score=max_score,
            instructor=request.user
        )
        
        # Add criteria
        criteria_count = int(request.POST.get('criteria_count', 0))
        for i in range(criteria_count):
            title = request.POST.get(f'criterion_title_{i}')
            max_score_criterion = request.POST.get(f'criterion_max_score_{i}')
            weight = request.POST.get(f'criterion_weight_{i}', 1.0)
            
            if title and max_score_criterion:
                RubricCriterion.objects.create(
                    rubric=rubric,
                    title=title,
                    max_score=max_score_criterion,
                    weight=weight,
                    order=i
                )
        
        messages.success(request, f'Rubric "{name}" created successfully!')
        return redirect('grading:rubric_detail', rubric_id=rubric.rubric_id)
    
    return render(request, 'grading/create_rubric.html')


@login_required
def rubric_detail(request, rubric_id):
    """View rubric details"""
    rubric = get_object_or_404(Rubric, rubric_id=rubric_id)
    
    # Check permissions
    if rubric.instructor != request.user and not rubric.is_public:
        messages.error(request, 'You do not have permission to view this rubric.')
        return redirect('grading:rubric_list')
    
    criteria = rubric.criteria.all().order_by('order')
    
    context = {
        'rubric': rubric,
        'criteria': criteria,
    }
    return render(request, 'grading/rubric_detail.html', context)


@login_required
def start_grading_session(request):
    """Start a new grading session"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can start grading sessions.')
        return redirect('core:dashboard')
    
    # Check for existing active session
    active_session = GradingSession.objects.filter(
        instructor=request.user,
        status='IN_PROGRESS'
    ).first()
    
    if active_session:
        messages.info(request, 'You already have an active grading session.')
        return redirect('grading:dashboard')
    
    # Create new session
    session = GradingSession.objects.create(
        instructor=request.user,
        status='IN_PROGRESS'
    )
    
    messages.success(request, 'Grading session started!')
    return redirect('grading:dashboard')

@login_required
def end_grading_session(request, session_id):
    """End a grading session"""
    session = get_object_or_404(GradingSession, session_id=session_id)
    
    if session.instructor != request.user:
        messages.error(request, 'You can only end your own grading sessions.')
        return redirect('grading:dashboard')
    
    session.status = 'COMPLETED'
    session.end_time = timezone.now()
    session.save()
    
    messages.success(request, 'Grading session ended.')
    return redirect('grading:dashboard')

@login_required
def simple_grade_submission(request, submission_id):
    """Simplified grading interface"""
    submission = get_object_or_404(Submission, submission_id=submission_id)
    
    # Check permissions
    if submission.exam.instructor != request.user and request.user.role != 'ADMIN':
        messages.error(request, 'You can only grade your own exams.')
        return redirect('grading:dashboard')
    
    # Redirect to the existing grade_submission view
    return redirect('grading:grade_submission', submission_id=submission_id)

@login_required
def bulk_grade_overview(request):
    """Bulk grading overview page"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can use bulk grading.')
        return redirect('core:dashboard')
    
    # Get exams with pending submissions
    exams = Exam.objects.filter(
        instructor=request.user,
        is_published=True,
        submissions__is_graded=False
    ).distinct()
    
    context = {
        'exams': exams,
    }
    
    return render(request, 'grading/bulk_overview.html', context)