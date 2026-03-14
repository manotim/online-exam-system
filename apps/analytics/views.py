# apps/analytics/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Avg, Max, Min, Q, Sum
from django.core.paginator import Paginator
from apps.exams.models import Exam, Course, Submission, Answer
from apps.users.models import CustomUser
from apps.analytics.services import (
    PerformanceAnalytics, 
    ExamAnalytics, 
    InstitutionalAnalytics,
    ReportingService
)

@login_required
def analytics_dashboard(request):
    """Main analytics dashboard - routes based on user role"""
    user = request.user
    
    if user.role == 'STUDENT':
        return student_performance(request, user.id)
    elif user.role == 'INSTRUCTOR':
        return instructor_dashboard(request)
    elif user.role == 'ADMIN':
        return admin_dashboard(request)
    
    return redirect('core:dashboard')

@login_required
def instructor_dashboard(request):
    """Analytics dashboard for instructors"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        messages.error(request, 'Only instructors can access this dashboard.')
        return redirect('analytics:dashboard')
    
    # Get instructor's courses
    courses = Course.objects.filter(instructor=request.user)
    
    # Get course performance
    course_performance = []
    for course in courses:
        performance = InstitutionalAnalytics.get_course_performance(course)
        course_performance.append(performance)
    
    # Get recent exams (last 5)
    recent_exams = Exam.objects.filter(
        instructor=request.user,
        is_published=True
    ).order_by('-end_date')[:5]
    
    # Get exam statistics
    exam_stats = []
    for exam in recent_exams:
        stats = ExamAnalytics.get_exam_statistics(exam)
        exam_stats.append(stats)
    
    # Calculate overall statistics
    total_students = 0
    for course in courses:
        total_students += course.enrollments.filter(is_active=True).count()
    
    # Get insights
    insights = []
    if len(course_performance) > 0:
        # Add some example insights
        avg_performance = sum(cp['overview']['average_score'] for cp in course_performance if 'overview' in cp) / len(course_performance)
        
        if avg_performance < 60:
            insights.append({
                'type': 'warning',
                'message': 'Overall student performance is below average. Consider reviewing course materials.'
            })
        elif avg_performance > 80:
            insights.append({
                'type': 'success',
                'message': 'Excellent overall student performance!'
            })
    
    context = {
        'courses': courses,
        'course_performance': course_performance,
        'recent_exams': recent_exams,
        'exam_stats': exam_stats,
        'total_courses': courses.count(),
        'total_exams': Exam.objects.filter(instructor=request.user).count(),
        'total_students': total_students,
        'active_courses': courses.count(),  # Simplified - you could filter by active
        'active_exams': recent_exams.count(),
        'active_students': total_students,
        'average_score': avg_performance if 'avg_performance' in locals() else 0,
        'student_rankings': [],  # You would populate this from InstitutionalAnalytics
        'insights': insights,
    }
    
    return render(request, 'analytics/instructor_dashboard.html', context)

@login_required
def student_performance(request, student_id=None):
    """View student performance analytics"""
    if student_id:
        # Instructor viewing specific student
        if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
            messages.error(request, 'Only instructors can view other students.')
            return redirect('analytics:dashboard')
        
        student = get_object_or_404(CustomUser, id=student_id)
    else:
        # Student viewing own performance
        if request.user.role != 'STUDENT':
            return redirect('analytics:dashboard')
        student = request.user
    
    # Get course filter
    course_id = request.GET.get('course_id')
    course = None
    if course_id:
        course = get_object_or_404(Course, course_id=course_id)
    
    # Get time period
    time_period_days = int(request.GET.get('time_period', 90))
    
    # Get performance data
    performance = PerformanceAnalytics.get_student_performance(
        student, 
        course=course,
        time_period_days=time_period_days
    )
    
    # Get enrolled courses (for filter dropdown)
    if student.role == 'STUDENT':
        enrolled_courses = Course.objects.filter(
            enrollments__student=student,
            enrollments__is_active=True
        ).distinct()
    else:
        enrolled_courses = Course.objects.filter(instructor=student)
    
    context = {
        'student': student,
        'performance': performance,
        'enrolled_courses': enrolled_courses,
        'selected_course': course,
        'time_period_days': time_period_days,
    }
    
    return render(request, 'analytics/student_performance.html', context)

@login_required
def exam_results(request, exam_id):
    """View detailed exam results for a student (keep your existing functionality)"""
    exam = get_object_or_404(Exam, exam_id=exam_id)
    user = request.user
    
    # Get student's submission
    submission = get_object_or_404(Submission, exam=exam, student=user)
    
    if not submission.submitted_at:
        messages.error(request, 'You have not submitted this exam yet.')
        return redirect('exams:exam_detail', exam_id=exam_id)
    
    # Get all answers for this submission
    answers = Answer.objects.filter(submission=submission).select_related('question')
    
    # Calculate statistics
    total_questions = exam.questions.count()
    answered_questions = answers.count()
    correct_answers = 0
    total_points = 0
    earned_points = 0
    
    for answer in answers:
        total_points += answer.question.points
        if answer.points_awarded:
            earned_points += answer.points_awarded
            if answer.points_awarded == answer.question.points:
                correct_answers += 1
    
    # Calculate percentages
    accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0
    score_percentage = (earned_points / total_points * 100) if total_points > 0 else 0
    
    # Get performance compared to others (if available)
    all_submissions = Submission.objects.filter(exam=exam, submitted_at__isnull=False)
    total_students = all_submissions.count()
    
    # Calculate percentile if there are other students
    percentile = None
    if total_students > 1:
        better_students = all_submissions.filter(total_score__gt=submission.total_score).count()
        percentile = ((total_students - better_students) / total_students) * 100
    
    # Prepare question-by-question analysis
    question_analysis = []
    for answer in answers:
        question_analysis.append({
            'question': answer.question,
            'answer': answer,
            'is_correct': answer.points_awarded == answer.question.points if answer.points_awarded else None,
            'points_earned': answer.points_awarded or 0,
            'max_points': answer.question.points,
        })
    
    context = {
        'exam': exam,
        'submission': submission,
        'answers': answers,
        'question_analysis': question_analysis,
        'stats': {
            'total_questions': total_questions,
            'answered_questions': answered_questions,
            'correct_answers': correct_answers,
            'accuracy': round(accuracy, 1),
            'total_points': total_points,
            'earned_points': earned_points,
            'score_percentage': round(score_percentage, 1),
            'total_students': total_students,
            'percentile': round(percentile, 1) if percentile else None,
        }
    }
    
    return render(request, 'analytics/exam_results.html', context)

@login_required
def exam_analytics(request, exam_id):
    """Detailed analytics for a specific exam"""
    exam = get_object_or_404(Exam, exam_id=exam_id)
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        if request.user.role == 'STUDENT' and exam.instructor != request.user:
            messages.error(request, 'Only instructors can view exam analytics.')
            return redirect('exams:exam_detail', exam_id=exam_id)
    
    stats = ExamAnalytics.get_exam_statistics(exam)
    
    # Get individual submissions for detailed view
    submissions = exam.submissions.filter(is_graded=True).select_related('student').order_by('-total_score')
    
    context = {
        'exam': exam,
        'stats': stats,
        'submissions': submissions,
    }
    
    return render(request, 'analytics/exam_analytics.html', context)

@login_required
def course_analytics(request, course_id):
    """Analytics for an entire course"""
    course = get_object_or_404(Course, course_id=course_id)
    
    # Check permissions
    if request.user.role not in ['INSTRUCTOR', 'ADMIN'] and course.instructor != request.user:
        messages.error(request, 'You do not have permission to view this course analytics.')
        return redirect('core:dashboard')
    
    performance = InstitutionalAnalytics.get_course_performance(course)
    
    # Get all exams in this course
    exams = Exam.objects.filter(course=course, is_published=True).order_by('-end_date')
    
    context = {
        'course': course,
        'performance': performance,
        'exams': exams,
    }
    
    return render(request, 'analytics/course_analytics.html', context)

@login_required
def performance_dashboard(request):
    """Student's overall performance dashboard - keep your existing functionality"""
    user = request.user
    
    # Get all submitted exams
    submissions = Submission.objects.filter(
        student=user, 
        submitted_at__isnull=False
    ).select_related('exam').order_by('-submitted_at')
    
    # Calculate overall statistics
    total_exams = submissions.count()
    average_score = 0
    best_score = 0
    worst_score = 100
    
    if total_exams > 0:
        total_scores = [s.total_score for s in submissions if s.total_score]
        if total_scores:
            average_score = sum(total_scores) / len(total_scores)
            best_score = max(total_scores)
            worst_score = min(total_scores)
    
    # Get recent activity
    recent_exams = submissions[:5]
    
    # Calculate progress over time (simplified)
    progress_data = []
    for i, submission in enumerate(submissions[:10][::-1]):
        if submission.total_score and submission.exam.total_points > 0:
            percentage = (submission.total_score / submission.exam.total_points) * 100
            progress_data.append({
                'exam': submission.exam.title,
                'score': float(percentage),
                'date': submission.submitted_at,
            })
    
    context = {
        'user': user,
        'submissions': submissions,
        'recent_exams': recent_exams,
        'stats': {
            'total_exams': total_exams,
            'average_score': round(average_score, 1),
            'best_score': round(best_score, 1),
            'worst_score': round(worst_score, 1),
        },
        'progress_data': progress_data,
    }
    
    return render(request, 'analytics/performance_dashboard.html', context)

@login_required
def export_report(request, report_type, object_id, format='json'):
    """Export analytics report in various formats"""
    if format not in ['json', 'csv']:
        messages.error(request, 'Invalid format. Use json or csv.')
        return redirect('analytics:dashboard')
    
    if report_type == 'exam':
        exam = get_object_or_404(Exam, exam_id=object_id)
        
        # Check permissions
        if exam.instructor != request.user and request.user.role != 'ADMIN':
            messages.error(request, 'You do not have permission to export this report.')
            return redirect('analytics:dashboard')
        
        report = ReportingService.generate_exam_report(exam, format)
        filename = f"exam_report_{exam.title.replace(' ', '_')}_{timezone.now().strftime('%Y%m%d')}.{format}"
    
    elif report_type == 'student':
        student = get_object_or_404(CustomUser, id=object_id)
        
        # Check permissions
        if request.user.role == 'STUDENT' and student != request.user:
            messages.error(request, 'You can only export your own report.')
            return redirect('analytics:dashboard')
        
        course_id = request.GET.get('course_id')
        course = get_object_or_404(Course, course_id=course_id) if course_id else None
        
        report = ReportingService.generate_student_report(student, course, format)
        filename = f"student_report_{student.email}_{timezone.now().strftime('%Y%m%d')}.{format}"
    
    else:
        messages.error(request, 'Invalid report type.')
        return redirect('analytics:dashboard')
    
    # Create HTTP response
    if format == 'json':
        response = HttpResponse(report, content_type='application/json')
    else:  # csv
        response = HttpResponse(report, content_type='text/csv')
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def api_exam_stats(request, exam_id):
    """API endpoint for exam statistics (for charts)"""
    exam = get_object_or_404(Exam, exam_id=exam_id)
    
    if exam.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    stats = ExamAnalytics.get_exam_statistics(exam)
    return JsonResponse(stats)

@login_required
def api_student_progress(request, student_id=None):
    """API endpoint for student progress data"""
    if student_id:
        student = get_object_or_404(CustomUser, id=student_id)
        if request.user.role not in ['INSTRUCTOR', 'ADMIN'] and student != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    else:
        if request.user.role != 'STUDENT':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        student = request.user
    
    performance = PerformanceAnalytics.get_student_performance(student)
    return JsonResponse(performance)

def admin_dashboard(request):
    """Analytics dashboard for administrators"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Only administrators can access this dashboard.')
        return redirect('analytics:dashboard')
    
    # Get overall statistics
    total_courses = Course.objects.count()
    total_exams = Exam.objects.count()
    total_students = CustomUser.objects.filter(role='STUDENT').count()
    total_instructors = CustomUser.objects.filter(role='INSTRUCTOR').count()
    
    # Get recent activity
    recent_submissions = Submission.objects.filter(
        submitted_at__isnull=False
    ).select_related('exam', 'student').order_by('-submitted_at')[:10]
    
    context = {
        'total_courses': total_courses,
        'total_exams': total_exams,
        'total_students': total_students,
        'total_instructors': total_instructors,
        'recent_submissions': recent_submissions,
    }
    
    return render(request, 'analytics/admin_dashboard.html', context)