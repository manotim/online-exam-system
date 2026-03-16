# apps/grading/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime
from django.utils import timezone
from django.db.models import Q, Count
from django.http import HttpResponseForbidden
from apps.exams.models import Exam, Submission, Answer
from apps.users.models import CustomUser
from apps.grading.models import (
    Rubric, RubricCriterion, GradingSession,
    SubmissionFlag, FlagComment, FlagHistory, BulkFlagOperation
)
from apps.grading.services import AutoGradingService, RubricGradingService, AnalyticsService, NotificationService


@login_required
def grading_dashboard(request):
    """Dashboard for instructors to see submissions needing grading"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can access grading.')
        return redirect('core:dashboard')
    
    # Get exams created by this instructor
    exams = Exam.objects.filter(instructor=request.user, is_published=True)
    
    # Get ALL submissions that need attention (including partially graded)
    pending_submissions = []
    all_pending_count = 0
    
    for exam in exams:
        # Get submissions that are submitted but not fully graded
        submissions = exam.submissions.filter(
            submitted_at__isnull=False
        ).exclude(
            grading_status='MANUALLY_GRADED'
        ).exclude(
            grading_status='AUTO_GRADED'
        ).select_related('student')
        
        for submission in submissions:
            # Count total answers vs graded answers
            total_answers = submission.answers.count()
            graded_answers = submission.answers.filter(points_awarded__isnull=False).count()
            
            # Check if there are any ungraded answers
            ungraded_exists = submission.answers.filter(points_awarded__isnull=True).exists()
            
            if ungraded_exists or graded_answers < total_answers:
                # Add submission info
                submission_info = {
                    'submission': submission,
                    'student': submission.student,
                    'exam': exam,
                    'submitted_at': submission.submitted_at,
                    'total_answers': total_answers,
                    'graded_answers': graded_answers,
                    'progress': int((graded_answers / total_answers) * 100) if total_answers > 0 else 0,
                    'needs_manual': submission.answers.filter(
                        question__question_type__in=['SHORT_ANSWER', 'ESSAY'],
                        points_awarded__isnull=True
                    ).exists()
                }
                pending_submissions.append(submission_info)
                all_pending_count += 1
    
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
    
    # Get recent grading activity
    recent_grading = Answer.objects.filter(
        grader=request.user,
        graded_at__isnull=False
    ).select_related(
        'question', 
        'submission', 
        'submission__student',
        'submission__exam'
    ).order_by('-graded_at')[:10]
    
    # Get exams with pending counts
    exam_stats = []
    for exam in exams:
        pending_count = Submission.objects.filter(
            exam=exam,
            submitted_at__isnull=False
        ).exclude(
            grading_status__in=['MANUALLY_GRADED', 'AUTO_GRADED']
        ).count()
        
        if pending_count > 0:
            exam_stats.append({
                'exam': exam,
                'pending': pending_count
            })
    
    # Get recent flags
    recent_flags = SubmissionFlag.objects.filter(
        exam__in=exams,
        status__in=['active', 'in_review']
    ).select_related('exam', 'flagged_by').order_by('-created_at')[:5]
    
    context = {
        'active_session': active_session,
        'pending_submissions': pending_submissions[:20],  # Show up to 20
        'recent_grading': recent_grading,
        'total_pending': all_pending_count,
        'total_graded': total_graded,
        'total_exams': exams.count(),
        'exam_stats': exam_stats,
        'recent_flags': recent_flags,
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
    """Grade a specific submission"""
    submission = get_object_or_404(
        Submission.objects.select_related('student', 'exam', 'exam__instructor'),
        submission_id=submission_id
    )
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can grade submissions.')
        return redirect('core:dashboard')
    
    if submission.exam.instructor != request.user and request.user.role != 'ADMIN':
        messages.error(request, 'You can only grade submissions for your own exams.')
        return redirect('grading:submissions_list')
    
    # Check if submission has active flags that block grading
    blocking_flags = SubmissionFlag.objects.filter(
        submission_id=submission.submission_id,
        status__in=['active', 'in_review'],
        hold_grading=True
    ).exists()
    
    if blocking_flags:
        messages.warning(request, 'This submission has active flags that block grading. Please resolve them first.')
        return redirect('grading:submissions_list')
    
    # Get or create grading session
    grading_session, created = GradingSession.objects.get_or_create(
        instructor=request.user,
        exam=submission.exam,
        status='IN_PROGRESS',
        defaults={'start_time': timezone.now()}
    )
    
    # Get all answers for this submission
    all_answers = submission.answers.select_related('question').order_by('question__position')
    
    # Separate auto-graded and manually graded answers
    auto_graded = []
    manual_graded = []
    
    for answer in all_answers:
        if answer.question.question_type in ['MCQ', 'TRUE_FALSE']:
            auto_graded.append(answer)
        else:
            manual_graded.append(answer)
    
    if request.method == 'POST':
        graded_count = 0
        
        # Handle manual grading
        for answer in manual_graded:
            points_key = f'points_{answer.answer_id}'
            feedback_key = f'feedback_{answer.answer_id}'
            
            if points_key in request.POST:
                try:
                    points = float(request.POST[points_key])
                    max_points = float(answer.question.points)
                    
                    if 0 <= points <= max_points:
                        answer.points_awarded = points
                        answer.manual_feedback = request.POST.get(feedback_key, '')
                        answer.grader = request.user
                        answer.graded_at = timezone.now()
                        answer.save()
                        graded_count += 1
                except (ValueError, TypeError):
                    continue
        
        # Update submission status using service
        if graded_count > 0:
            AutoGradingService.update_submission_status(submission)
            
            # Update grading session
            grading_session.submissions_graded += 1
            grading_session.save()
            
            messages.success(request, f'Graded {graded_count} answers.')
        else:
            messages.warning(request, 'No grades were saved.')
        
        # Check which button was clicked
        if 'save_and_continue' in request.POST:
            return redirect('grading:grade_submission', submission_id=submission_id)
        elif 'save_and_next' in request.POST:
            # Find next ungraded submission for this exam
            next_submission = Submission.objects.filter(
                exam=submission.exam,
                submitted_at__isnull=False,
                is_graded=False
            ).exclude(submission_id=submission_id).first()
            
            if next_submission:
                return redirect('grading:grade_submission', submission_id=next_submission.submission_id)
            else:
                messages.info(request, 'No more submissions to grade for this exam.')
                return redirect('grading:submissions_list_by_exam', exam_id=submission.exam.exam_id)
        else:
            return redirect('grading:submissions_list_by_exam', exam_id=submission.exam.exam_id)
    
    # Calculate progress
    total_questions = len(all_answers)
    graded_questions = len([a for a in all_answers if a.points_awarded is not None])
    progress = int((graded_questions / total_questions) * 100) if total_questions > 0 else 0
    
    # Get active flags for this submission
    active_flags = SubmissionFlag.objects.filter(
        submission_id=submission.submission_id,
        status__in=['active', 'in_review']
    ).select_related('flagged_by').order_by('-created_at')
    
    context = {
        'submission': submission,
        'student': submission.student,
        'exam': submission.exam,
        'auto_graded': auto_graded,
        'manual_graded': manual_graded,
        'grading_session': grading_session,
        'total_questions': total_questions,
        'graded_questions': graded_questions,
        'progress': progress,
        'active_flags': active_flags,
    }
    
    return render(request, 'grading/grade_submission.html', context)


@login_required
def flag_submission(request, submission_id):
    """
    Flag a submission for review or mark it as problematic.
    """
    submission = get_object_or_404(Submission, submission_id=submission_id)
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can flag submissions.')
        return redirect('core:dashboard')
    
    if submission.exam.instructor != request.user and request.user.role != 'ADMIN':
        messages.error(request, 'You can only flag submissions for your own exams.')
        return redirect('grading:submissions_list')
    
    if request.method == 'POST':
        # Check if there's already an active flag for this submission
        existing_flag = SubmissionFlag.objects.filter(
            submission_id=submission_id,
            status__in=['active', 'in_review']
        ).first()
        
        if existing_flag and request.POST.get('action') != 'force_new':
            messages.warning(request, 'This submission already has an active flag.')
            return redirect('grading:view_flag', flag_id=existing_flag.flag_id)
        
        # Create new flag
        flag = SubmissionFlag.objects.create(
            submission_id=submission_id,
            exam=submission.exam,
            flagged_by=request.user,
            flag_type=request.POST.get('flag_type', 'other'),
            severity=request.POST.get('severity', 'medium'),
            reason=request.POST.get('reason', ''),
            additional_notes=request.POST.get('additional_notes', ''),
            hold_grading=request.POST.get('hold_grading') == 'on',
            notify_student=request.POST.get('notify_student') == 'on',
            notify_admin=request.POST.get('notify_admin') == 'on',
        )
        
        # Create history entry
        FlagHistory.objects.create(
            flag=flag,
            changed_by=request.user,
            change_type='created',
            new_value=f"Flag created with type: {flag.flag_type}, severity: {flag.severity}"
        )
        
        messages.success(request, 'Submission flagged successfully.')
        
        # Check if user wants to escalate immediately
        if request.POST.get('action') == 'flag_and_escalate':
            flag.status = 'in_review'
            flag.save()
            
            FlagHistory.objects.create(
                flag=flag,
                changed_by=request.user,
                change_type='status_change',
                old_value='active',
                new_value='in_review'
            )
            
            messages.info(request, 'Flag has been escalated for review.')
        
        # Determine redirect
        next_url = request.POST.get('next', 'grading:submissions_list')
        if next_url == 'grade':
            return redirect('grading:grade_submission', submission_id=submission_id)
        else:
            return redirect(next_url)
    
    # GET request - show form
    # Check for existing flags
    existing_flags = SubmissionFlag.objects.filter(
        submission_id=submission_id
    ).select_related('flagged_by').order_by('-created_at')
    
    # Get the next URL to redirect to after flagging
    next_url = request.GET.get('next', 'grading:submissions_list')
    
    context = {
        'submission': submission,
        'existing_flags': existing_flags,
        'next_url': next_url,
    }
    return render(request, 'grading/flag_submission.html', context)


@login_required
def view_flag(request, flag_id):
    """
    View details of a specific flag
    """
    flag = get_object_or_404(
        SubmissionFlag.objects.select_related('exam', 'flagged_by', 'resolved_by'),
        flag_id=flag_id
    )
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('core:dashboard')
    
    if flag.exam.instructor != request.user and request.user.role != 'ADMIN':
        messages.error(request, 'You can only view flags for your own exams.')
        return redirect('grading:dashboard')
    
    # Get the submission
    submission = get_object_or_404(Submission, submission_id=flag.submission_id)
    
    comments = flag.comments.all().select_related('user')
    history = flag.history.all().select_related('changed_by')
    
    if request.method == 'POST':
        # Add comment
        if request.POST.get('comment'):
            comment = FlagComment.objects.create(
                flag=flag,
                user=request.user,
                comment=request.POST['comment']
            )
            
            FlagHistory.objects.create(
                flag=flag,
                changed_by=request.user,
                change_type='comment_added',
                new_value=f"Comment added: {request.POST['comment'][:50]}..."
            )
            
            messages.success(request, 'Comment added.')
        
        # Update status
        if request.POST.get('status') and request.POST['status'] in dict(SubmissionFlag.FLAG_STATUS):
            old_status = flag.get_status_display()
            flag.status = request.POST['status']
            flag.save()
            
            FlagHistory.objects.create(
                flag=flag,
                changed_by=request.user,
                change_type='status_change',
                old_value=old_status,
                new_value=flag.get_status_display()
            )
            messages.success(request, f'Flag status updated to {flag.get_status_display()}.')
        
        # Update severity
        if request.POST.get('severity') and request.POST['severity'] in dict(SubmissionFlag.SEVERITY_LEVELS):
            old_severity = flag.get_severity_display()
            flag.severity = request.POST['severity']
            flag.save()
            
            FlagHistory.objects.create(
                flag=flag,
                changed_by=request.user,
                change_type='severity_change',
                old_value=old_severity,
                new_value=flag.get_severity_display()
            )
            messages.success(request, f'Severity updated to {flag.get_severity_display()}.')
        
        # Resolve flag
        if request.POST.get('resolve'):
            flag.status = 'resolved'
            flag.resolved_at = timezone.now()
            flag.resolved_by = request.user
            flag.resolution_notes = request.POST.get('resolution_notes', '')
            flag.save()
            
            FlagHistory.objects.create(
                flag=flag,
                changed_by=request.user,
                change_type='resolved',
                new_value=f"Resolved: {flag.resolution_notes[:50]}..."
            )
            
            messages.success(request, 'Flag resolved.')
        
        return redirect('grading:view_flag', flag_id=flag.flag_id)
    
    context = {
        'flag': flag,
        'submission': submission,
        'comments': comments,
        'history': history,
    }
    return render(request, 'grading/view_flag.html', context)


@login_required
def bulk_grade(request, exam_id):
    """Bulk grading interface for an exam"""
    exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
    
    if request.method == 'POST':
        graded_count = 0
        
        # Handle bulk grading
        for key, value in request.POST.items():
            if key.startswith('points_'):
                parts = key.split('_')
                if len(parts) == 3:  # points_answerId_questionId
                    answer_id = parts[1]
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
    submissions = exam.submissions.filter(
        submitted_at__isnull=False
    ).select_related('student').order_by('student__email')
    
    # Get questions that need manual grading
    questions = exam.questions.filter(
        question_type__in=['SHORT_ANSWER', 'ESSAY']
    ).order_by('position')
    
    # Prepare data for template
    grading_data = []
    for submission in submissions:
        student_answers = {}
        for question in questions:
            answer = Answer.objects.filter(
                submission=submission,
                question=question
            ).first()
            student_answers[str(question.question_id)] = answer
        
        # Check if submission has flags
        has_flags = SubmissionFlag.objects.filter(
            submission_id=submission.submission_id,
            status__in=['active', 'in_review']
        ).exists()
        
        grading_data.append({
            'submission': submission,
            'answers': student_answers,
            'has_flags': has_flags,
        })
    
    context = {
        'exam': exam,
        'grading_data': grading_data,
        'questions': questions,
        'submissions': submissions,
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
    
    # Get all answers with related question data
    answers = submission.answers.select_related('question').order_by('question__position')
    
    # Calculate statistics
    total_questions = answers.count()
    correct_count = 0
    partial_count = 0
    incorrect_count = 0
    total_points_earned = 0
    total_points_possible = 0
    
    for answer in answers:
        question = answer.question
        total_points_possible += float(question.points)
        
        if answer.points_awarded is not None:
            total_points_earned += float(answer.points_awarded)
            
            # Check if answer is correct, partial, or incorrect
            if float(answer.points_awarded) >= float(question.points) * 0.99:  # Within 1% of max points
                correct_count += 1
            elif float(answer.points_awarded) > 0:
                partial_count += 1
            else:
                incorrect_count += 1
        else:
            # Not graded yet
            incorrect_count += 1
    
    # Calculate percentage
    if total_points_possible > 0:
        percentage = (total_points_earned / total_points_possible) * 100
    else:
        percentage = 0
    
    context = {
        'submission': submission,
        'exam': submission.exam,
        'answers': answers,
        'stats': {
            'total_questions': total_questions,
            'correct_count': correct_count,
            'partial_count': partial_count,
            'incorrect_count': incorrect_count,
            'total_points_earned': round(total_points_earned, 2),
            'total_points_possible': total_points_possible,
            'percentage': round(percentage, 1),
        }
    }
    
    return render(request, 'grading/view_feedback.html', context)


@login_required
def publish_grades(request, exam_id):
    """Publish grades for an exam"""
    exam = get_object_or_404(Exam, exam_id=exam_id, instructor=request.user)
    
    # Check for any unresolved flags that might block publishing
    unresolved_flags = SubmissionFlag.objects.filter(
        exam=exam,
        status__in=['active', 'in_review'],
        hold_grading=True
    ).exists()
    
    if unresolved_flags:
        messages.warning(request, 'There are unresolved flags for this exam. Please resolve them before publishing.')
        return redirect('grading:submissions_list_by_exam', exam_id=exam_id)
    
    if request.method == 'POST':
        # Use NotificationService to publish grades
        result = NotificationService.bulk_publish_grades(exam)
        
        messages.success(request, f'Published grades for {result["total_published"]} submissions.')
        return redirect('grading:submissions_list_by_exam', exam_id=exam_id)
    
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
        
        # Get flag statistics
        flag_stats = SubmissionFlag.objects.filter(exam=exam).aggregate(
            total_flags=Count('flag_id'),
            active_flags=Count('flag_id', filter=Q(status__in=['active', 'in_review'])),
            resolved_flags=Count('flag_id', filter=Q(status='resolved')),
        )
        
        context = {
            'exam': exam,
            'distributions': distributions,
            'exam_distribution': exam_distribution,
            'flag_stats': flag_stats,
        }
        
        return render(request, 'grading/exam_analytics.html', context)
    else:
        # Overall analytics for instructor
        efficiency = AnalyticsService.get_grading_efficiency(request.user)
        
        # Get overall flag statistics
        exams = Exam.objects.filter(instructor=request.user)
        flag_stats = SubmissionFlag.objects.filter(exam__in=exams).aggregate(
            total_flags=Count('flag_id'),
            active_flags=Count('flag_id', filter=Q(status__in=['active', 'in_review'])),
            resolved_flags=Count('flag_id', filter=Q(status='resolved')),
        )
        
        context = {
            'efficiency': efficiency,
            'flag_stats': flag_stats,
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
    from django.db.models import Count, Q, OuterRef, Subquery
    
    exams = Exam.objects.filter(
        instructor=request.user,
        is_published=True
    ).annotate(
        pending_count=Count(
            'submissions',
            filter=Q(submissions__submitted_at__isnull=False) & 
                   ~Q(submissions__grading_status__in=['MANUALLY_GRADED', 'AUTO_GRADED'])
        ),
        total_submissions=Count(
            'submissions',
            filter=Q(submissions__submitted_at__isnull=False)
        )
    ).filter(pending_count__gt=0)
    
    # Calculate graded count for each exam
    exam_list = []
    total_pending = 0
    total_questions_sum = 0
    
    for exam in exams:
        # Get graded submissions count
        graded_count = Submission.objects.filter(
            exam=exam,
            submitted_at__isnull=False,
            is_graded=True
        ).count()
        
        # Get total questions
        total_questions = exam.questions.count()
        total_questions_sum += total_questions
        
        # Get flag count for this exam
        flag_count = SubmissionFlag.objects.filter(
            exam=exam,
            status__in=['active', 'in_review']
        ).count()
        
        exam_data = {
            'exam': exam,
            'pending_count': exam.pending_count,
            'graded_count': graded_count,
            'total_submissions': exam.total_submissions,
            'total_questions': total_questions,
            'mcq_count': exam.questions.filter(question_type='MCQ').count(),
            'tf_count': exam.questions.filter(question_type='TRUE_FALSE').count(),
            'essay_count': exam.questions.filter(question_type__in=['ESSAY', 'SHORT_ANSWER']).count(),
            'flag_count': flag_count,
        }
        exam_list.append(exam_data)
        total_pending += exam.pending_count
    
    avg_questions = total_questions_sum / len(exam_list) if exam_list else 0
    
    context = {
        'exams': exam_list,
        'total_pending': total_pending,
        'avg_questions': avg_questions,
    }
    
    return render(request, 'grading/bulk_overview.html', context)