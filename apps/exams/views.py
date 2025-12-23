# apps/exams/views.py - Add these functions
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .utils import can_access_exam, validate_exam_timing, prepare_exam_context, calculate_time_remaining
from .models import Exam, Question, Submission, Answer, Course
from apps.grading.services import AutoGradingService

@login_required
def exam_list(request):
    user = request.user
    
    if user.role == 'INSTRUCTOR':
        # Show exams created by instructor
        exams = Exam.objects.filter(instructor=user).order_by('-created_at')
    elif user.role == 'STUDENT':
        # Show published exams
        exams = Exam.objects.filter(is_published=True).order_by('-created_at')
    else:  # ADMIN
        # Show all exams
        exams = Exam.objects.all().order_by('-created_at')
    
    context = {
        'exams': exams,
        'now': timezone.now()
    }
    return render(request, 'exams/exam_list.html', context)

@login_required
def create_exam(request):
    # Only instructors and admins can create exams
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors and administrators can create exams.')
        return redirect('exams:exam_list')
    
    # Simple implementation for now - redirect to admin
    messages.info(request, 'Redirecting to admin panel to create exam.')
    return redirect('/admin/exams/exam/add/')

# apps/exams/views.py - Import the helper


@login_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, exam_id=exam_id)
    user = request.user
    
    print(f"DEBUG: User: {user.email}, Role: {user.role}")
    print(f"DEBUG: Exam: {exam.title}, Published: {exam.is_published}")
    print(f"DEBUG: Exam Instructor: {exam.instructor.email if exam.instructor else 'None'}")
    
    # DEBUG: Call can_access_exam and check what it returns
    result = can_access_exam(user, exam)
    print(f"DEBUG: can_access_exam returned: {result}")
    print(f"DEBUG: Type of result: {type(result)}")
    print(f"DEBUG: Is tuple? {isinstance(result, tuple)}")
    print(f"DEBUG: Is bool? {isinstance(result, bool)}")
    
    # Safe unpacking
    if isinstance(result, tuple) and len(result) == 2:
        can_access, reason = result
        print(f"DEBUG: Unpacked - can_access: {can_access}, reason: {reason}")
    elif isinstance(result, bool):
        can_access = result
        reason = "Boolean result returned"
        print(f"DEBUG: Boolean result - can_access: {can_access}")
    else:
        # Unexpected type
        print(f"DEBUG: ERROR - Unexpected return type: {type(result)}")
        can_access = False
        reason = f"System error: Unexpected return type {type(result)}"
    
    if not can_access and user.role == 'STUDENT':
        # Special case: check if they have a submission to view results
        submission = Submission.objects.filter(exam=exam, student=user).first()
        if submission and submission.submitted_at:
            print(f"DEBUG: Student has submission, allowing access")
            can_access = True
            reason = "Viewing results of completed exam"
        else:
            print(f"DEBUG: Student access denied: {reason}")
            messages.error(request, reason)
            return redirect('exams:exam_list')
    elif not can_access:
        print(f"DEBUG: Access denied for {user.role}: {reason}")
        messages.error(request, reason)
        return redirect('exams:exam_list')
    
    # Get submission for this student (if exists)
    submission = Submission.objects.filter(exam=exam, student=user).first()
    print(f"DEBUG: Submission found: {submission is not None}")
    
    # Prepare context using utility
    try:
        context = prepare_exam_context(exam, user, submission)
    except Exception as e:
        print(f"DEBUG: Error in prepare_exam_context: {e}")
        context = {
            'exam': exam,
            'questions': exam.questions.all().order_by('position'),
            'answers': {},
            'submission': submission
        }
    
    # Add extra context
    context.update({
        'can_access': can_access,
        'access_reason': reason,
        'has_results': False,
        'submission': submission,
    })
    
    # Check if student has graded results
    if user.role == 'STUDENT' and submission:
        if submission.submitted_at and submission.is_graded:
            context['has_results'] = True
            print(f"DEBUG: Student has graded results")
        
        # Calculate time remaining if exam is in progress
        if submission.started_at and not submission.submitted_at:
            time_remaining = calculate_time_remaining(submission, exam)
            context['time_remaining'] = time_remaining
            print(f"DEBUG: Time remaining: {time_remaining}")
    
    # For instructors, add submission statistics
    if user.role in ['INSTRUCTOR', 'ADMIN']:
        total_submissions = exam.submissions.count()
        graded_submissions = exam.submissions.filter(is_graded=True).count()
        
        context.update({
            'total_submissions': total_submissions,
            'graded_submissions': graded_submissions,
            'submissions': exam.submissions.select_related('student').order_by('-submitted_at')[:10]
        })
        print(f"DEBUG: Instructor view - Submissions: {total_submissions}, Graded: {graded_submissions}")
    
    print(f"DEBUG: Rendering template with context keys: {list(context.keys())}")
    return render(request, 'exams/exam_detail.html', context)


@login_required
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam, exam_id=exam_id)
    user = request.user
    
    # BASIC ROLE VALIDATION
    if user.role != 'STUDENT':
        return redirect('exams:exam_detail', exam_id=exam_id)
    
    # USE UTILITY FOR VALIDATION
    is_valid, message = validate_exam_timing(exam, user)
    if not is_valid:
        messages.error(request, message)
        return redirect('exams:exam_detail', exam_id=exam_id)
    
    # Get or create submission
    submission, created = Submission.objects.get_or_create(
        exam=exam,
        student=user,
        defaults={'started_at': timezone.now()}
    )
    
    # Check if already submitted
    if submission.submitted_at:
        messages.info(request, 'You have already submitted this exam.')
        return redirect('exams:exam_detail', exam_id=exam_id)
    
    # Get questions
    questions = exam.questions.all().order_by('position')
    
    if request.method == 'POST':
        # SAVE ANSWERS
        for question in questions:
            answer_key = f'question_{question.question_id}'
            
            if question.question_type in ['MCQ', 'TRUE_FALSE']:
                # For multiple choice, get selected value
                answer_value = request.POST.get(answer_key, '').strip()
                
                if answer_value:
                    Answer.objects.update_or_create(
                        submission=submission,
                        question=question,
                        defaults={
                            'answer_text': answer_value,
                            'selected_options': [answer_value]
                        }
                    )
            elif question.question_type in ['SHORT_ANSWER', 'ESSAY']:
                # For text answers
                answer_value = request.POST.get(answer_key, '').strip()
                
                if answer_value:
                    Answer.objects.update_or_create(
                        submission=submission,
                        question=question,
                        defaults={
                            'answer_text': answer_value,
                            'selected_options': []
                        }
                    )
            else:
                # Handle multiple-select MCQs (not currently implemented)
                answer_values = request.POST.getlist(answer_key + '[]')
                if answer_values:
                    Answer.objects.update_or_create(
                        submission=submission,
                        question=question,
                        defaults={
                            'answer_text': ', '.join(answer_values),
                            'selected_options': answer_values
                        }
                    )
        
        # Check which button was clicked
        if 'submit_exam' in request.POST:
            submission.submitted_at = timezone.now()
            
            # USE AutoGradingService FOR AUTO-GRADING - UPDATED
            objective_score = AutoGradingService.auto_grade_submission(submission)
            
            # USE AutoGradingService FOR STATUS UPDATES - UPDATED
            AutoGradingService.update_submission_status(submission)
            
            messages.success(request, f'Exam submitted successfully! Score: {objective_score}/{exam.total_points}')
            return redirect('exams:exam_detail', exam_id=exam_id)
        else:
            # Save progress without submitting
            messages.success(request, 'Progress saved!')
            return redirect('exams:take_exam', exam_id=exam_id)
    
    # USE UTILITY FOR CONTEXT PREPARATION
    context = prepare_exam_context(exam, user, submission)
    
    # Add questions to context
    context['questions'] = questions
    
    # USE UTILITY FOR TIME CALCULATION
    if exam.time_limit_minutes and submission.started_at:
        context['time_remaining'] = calculate_time_remaining(exam, submission)
    
    return render(request, 'exams/very_simple_take_exam.html', context)


# Placeholder functions for edit and delete
@login_required
def edit_exam(request, exam_id):
    messages.info(request, 'Edit functionality coming soon. Use admin panel for now.')
    return redirect('/admin/exams/exam/' + str(exam_id) + '/change/')

@login_required
def delete_exam(request, exam_id):
    messages.info(request, 'Delete functionality coming soon. Use admin panel for now.')
    return redirect('exams:exam_list')