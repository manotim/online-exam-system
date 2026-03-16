# apps/exams/views.py 
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .utils import can_access_exam, validate_exam_timing, prepare_exam_context, calculate_time_remaining
from .models import Exam, Question, Submission, Answer, Course
from apps.grading.services import AutoGradingService
from django.db.models import Q, Count
from .models import Course, Enrollment
from .forms import CourseForm, CourseFilterForm
from apps.users.models import Institution
from django.db import models

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




# Add to apps/exams/views.py - TEMPORARY DEBUG VIEW

@login_required
def debug_submissions(request):
    """Debug view to check submissions (temporary)"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    submissions = Submission.objects.filter(
        exam__instructor=request.user
    ).select_related('student', 'exam').order_by('-submitted_at')
    
    output = "<h1>Submissions Debug</h1>"
    output += "<table border='1' cellpadding='5'>"
    output += "<tr><th>ID</th><th>Student</th><th>Exam</th><th>Submitted</th><th>Graded</th><th>Status</th><th>Answers</th></tr>"
    
    for sub in submissions:
        answers_count = sub.answers.count()
        graded_answers = sub.answers.filter(points_awarded__isnull=False).count()
        
        output += f"<tr>"
        output += f"<td>{sub.submission_id}</td>"
        output += f"<td>{sub.student.email}</td>"
        output += f"<td>{sub.exam.title}</td>"
        output += f"<td>{'Yes' if sub.submitted_at else 'No'}</td>"
        output += f"<td>{'Yes' if sub.is_graded else 'No'}</td>"
        output += f"<td>{sub.grading_status}</td>"
        output += f"<td>{answers_count} total, {graded_answers} graded</td>"
        output += f"</tr>"
    
    output += "</table>"
    
    return HttpResponse(output)



@login_required
def course_list(request):
    """Display list of courses based on user role"""
    user = request.user
    
    # Get search query from request
    search_query = request.GET.get('search', '')
    
    # Base queryset based on user role
    if user.role == 'ADMIN':
        # Admins see all courses
        courses = Course.objects.all()
    elif user.role == 'INSTRUCTOR':
        # Instructors see courses they teach
        courses = Course.objects.filter(instructor=user)
    else:  # STUDENT
        # Students see courses they're enrolled in
        courses = Course.objects.filter(
            enrollment__student=user,  # Changed from enrollments to enrollment
            enrollment__is_active=True
        )
    
    # Apply search filter if provided
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Order by created date
    courses = courses.order_by('-created_at')
    
    # Get counts for each course - FIXED the related_name issue
    for course in courses:
        # Use the correct related_name from the Enrollment model
        # Looking at your error message, the related_name is 'enrollment' (singular)
        course.student_count = Enrollment.objects.filter(
            course=course, 
            is_active=True
        ).count()
        course.exam_count = course.exam_set.count()
    
    context = {
        'courses': courses,
        'search_query': search_query,
        'total_courses': courses.count(),
        'can_create': user.role in ['INSTRUCTOR', 'ADMIN'],
    }
    
    return render(request, 'exams/course_list.html', context)



@login_required
def course_create(request):
    """Create a new course"""
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors and administrators can create courses.')
        return redirect('exams:course_list')
    
    if request.method == 'POST':
        form = CourseForm(request.POST, user=request.user)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.save()
            messages.success(request, f'Course "{course.title}" created successfully!')
            return redirect('exams:course_detail', course_id=course.course_id)
        else:
            # Form errors will be displayed in template
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseForm(user=request.user)
    
    # Get institutions for dropdown
    institutions = Institution.objects.all()
    
    context = {
        'form': form,
        'institutions': institutions,
        'is_edit': False,
    }
    
    return render(request, 'exams/course_form.html', context)


@login_required
def course_detail(request, course_id):
    """Display detailed view of a course"""
    course = get_object_or_404(Course, course_id=course_id)
    user = request.user
    
    # Check permissions
    if user.role == 'STUDENT':
        # Check if student is enrolled - FIXED related_name
        if not Enrollment.objects.filter(student=user, course=course, is_active=True).exists():
            messages.error(request, 'You are not enrolled in this course.')
            return redirect('exams:course_list')
    elif user.role == 'INSTRUCTOR':
        # Check if instructor teaches this course
        if course.instructor != user:
            messages.error(request, 'You do not have permission to view this course.')
            return redirect('exams:course_list')
    # Admins can view all courses
    
    # Get exams for this course
    exams = course.exam_set.filter(is_published=True).order_by('-created_at')
    
    # Get enrolled students with their info - FIXED related_name
    enrollments = Enrollment.objects.filter(
        course=course, 
        is_active=True
    ).select_related('student').order_by('student__email')
    
    enrolled_students = [e.student for e in enrollments]
    
    # Check if current user is enrolled (for students)
    is_enrolled = False
    if user.role == 'STUDENT':
        is_enrolled = Enrollment.objects.filter(student=user, course=course, is_active=True).exists()
    
    # Calculate course statistics
    total_submissions = 0
    average_score = None
    
    if exams.exists():
        from apps.exams.models import Submission
        submissions = Submission.objects.filter(exam__in=exams, submitted_at__isnull=False)
        total_submissions = submissions.count()
        
        if total_submissions > 0:
            from django.db.models import Avg
            avg = submissions.filter(is_graded=True).aggregate(avg_score=Avg('total_score'))
            average_score = avg['avg_score']
    
    context = {
        'course': course,
        'exams': exams,
        'enrolled_students': enrolled_students[:10],  # Show first 10
        'student_count': len(enrolled_students),
        'exam_count': exams.count(),
        'total_submissions': total_submissions,
        'average_score': average_score,
        'is_enrolled': is_enrolled,
        'can_edit': user.role in ['ADMIN'] or (user.role == 'INSTRUCTOR' and course.instructor == user),
        'can_delete': user.role in ['ADMIN'] or (user.role == 'INSTRUCTOR' and course.instructor == user),
    }
    
    return render(request, 'exams/course_detail.html', context)


@login_required
def course_edit(request, course_id):
    """Edit an existing course"""
    course = get_object_or_404(Course, course_id=course_id)
    
    # Check permissions
    if request.user.role not in ['ADMIN'] and (request.user.role == 'INSTRUCTOR' and course.instructor != request.user):
        messages.error(request, 'You do not have permission to edit this course.')
        return redirect('exams:course_detail', course_id=course_id)
    
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Course "{course.title}" updated successfully!')
            return redirect('exams:course_detail', course_id=course.course_id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CourseForm(instance=course, user=request.user)
    
    institutions = Institution.objects.all()
    
    context = {
        'form': form,
        'course': course,
        'institutions': institutions,
        'is_edit': True,
    }
    
    return render(request, 'exams/course_form.html', context)


@login_required
def course_delete(request, course_id):
    """Delete a course"""
    course = get_object_or_404(Course, course_id=course_id)
    
    # Check permissions
    if request.user.role not in ['ADMIN'] and (request.user.role == 'INSTRUCTOR' and course.instructor != request.user):
        messages.error(request, 'You do not have permission to delete this course.')
        return redirect('exams:course_detail', course_id=course_id)
    
    # Check if course has exams
    exam_count = course.exam_set.count()
    
    if request.method == 'POST':
        course_title = course.title
        course.delete()
        messages.success(request, f'Course "{course_title}" deleted successfully!')
        return redirect('exams:course_list')
    
    context = {
        'course': course,
        'exam_count': exam_count,
    }
    
    return render(request, 'exams/course_confirm_delete.html', context)


@login_required
def submissions_for_exam(request, exam_id):
    """View all submissions for a specific exam"""
    exam = get_object_or_404(Exam, exam_id=exam_id)
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN'] and exam.instructor != request.user:
        messages.error(request, 'You do not have permission to view these submissions.')
        return redirect('exams:exam_detail', exam_id=exam_id)
    
    # Get all submissions for this exam
    submissions = exam.submissions.filter(
        submitted_at__isnull=False
    ).select_related('student').order_by('-submitted_at')
    
    # Filter by grading status if requested
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'graded':
        submissions = submissions.filter(is_graded=True)
    elif status_filter == 'pending':
        submissions = submissions.filter(is_graded=False)
    
    context = {
        'exam': exam,
        'submissions': submissions,
        'total_count': submissions.count(),
        'graded_count': submissions.filter(is_graded=True).count(),
        'pending_count': submissions.filter(is_graded=False).count(),
        'status_filter': status_filter,
    }
    
    return render(request, 'exams/submissions_for_exam.html', context)