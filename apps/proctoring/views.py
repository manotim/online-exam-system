# apps/proctoring/views.py
import json
import os
import base64
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.conf import settings
from apps.exams.models import Submission, Exam
from .models import ProctoringSession, SuspiciousActivity, ProctoringScreenshot

# =============================================
# CORE VIEW FUNCTIONS
# =============================================

@login_required
def home(request):
    """Proctoring home page - redirects to dashboard"""
    return redirect('proctoring:dashboard')

@login_required
def dashboard(request):
    """Instructor proctoring dashboard"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    # Get instructor's exams with proctoring
    exams = Exam.objects.filter(
        instructor=request.user,
        require_secure_browser=True
    )
    
    # Get all proctoring sessions for these exams
    session_ids = Submission.objects.filter(
        exam__in=exams
    ).values_list('proctoring_session__session_id', flat=True)
    
    sessions = ProctoringSession.objects.filter(
        session_id__in=session_ids
    ).select_related('submission', 'submission__student', 'submission__exam')
    
    # Calculate counts
    active_count = sessions.filter(status='ACTIVE').count()
    flagged_count = sessions.filter(status='FLAGGED').count()
    completed_count = sessions.filter(status='COMPLETED').count()
    
    context = {
        'sessions': sessions,
        'exams': exams,
        'active_count': active_count,
        'flagged_count': flagged_count,
        'completed_count': completed_count,
        'total_sessions': sessions.count(),
    }
    return render(request, 'proctoring/dashboard.html', context)

@login_required
def session_list(request):
    """List all proctoring sessions (for instructors/admins)"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    sessions = ProctoringSession.objects.select_related(
        'submission', 
        'submission__student', 
        'submission__exam'
    ).order_by('-start_time')
    
    # Apply filters
    status_filter = request.GET.get('status')
    student_filter = request.GET.get('student')
    
    if status_filter:
        sessions = sessions.filter(status=status_filter)
    if student_filter:
        sessions = sessions.filter(submission__student__email__icontains=student_filter)
    
    context = {
        'sessions': sessions
    }
    return render(request, 'proctoring/session_list.html', context)

@login_required
def session_detail(request, session_id):
    """Detail view for a proctoring session"""
    session = get_object_or_404(
        ProctoringSession.objects.select_related(
            'submission',
            'submission__student',
            'submission__exam'
        ),
        session_id=session_id
    )
    
    # Check permission
    if request.user.role not in ['INSTRUCTOR', 'ADMIN'] and request.user != session.student:
        return HttpResponseForbidden("Access denied")
    
    activities = session.activities.all().order_by('-timestamp')
    screenshots = session.screenshots.all().order_by('-timestamp')
    
    context = {
        'session': session,
        'activities': activities,
        'screenshots': screenshots,
    }
    return render(request, 'proctoring/session_detail.html', context)

# =============================================
# API ENDPOINTS
# =============================================

@csrf_exempt
@require_POST
def start_proctoring_session(request):
    """API to start a proctoring session (called from exam taking page)"""
    try:
        data = json.loads(request.body)
        submission_id = data.get('submission_id')
        
        if not submission_id:
            return JsonResponse({'success': False, 'error': 'No submission_id provided'})
        
        submission = get_object_or_404(Submission, submission_id=submission_id)
        
        # Check if session already exists
        existing_session = ProctoringSession.objects.filter(submission=submission).first()
        if existing_session:
            return JsonResponse({
                'success': True,
                'session_id': str(existing_session.session_id),
                'created': False,
                'message': 'Session already exists'
            })
        
        # Create proctoring session
        session = ProctoringSession.objects.create(
            submission=submission,
            student=submission.student,
            browser_name=data.get('browser_name', ''),
            browser_version=data.get('browser_version', ''),
            os_info=data.get('os_info', ''),
            screen_resolution=data.get('screen_resolution', ''),
            status='ACTIVE'
        )
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'created': True,
            'message': 'Session created successfully'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def log_suspicious_activity(request):
    """API to log suspicious activities"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        activity_type = data.get('activity_type')
        
        if not session_id or not activity_type:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        session = get_object_or_404(ProctoringSession, session_id=session_id)
        
        # Update session counters based on activity type
        if activity_type == 'TAB_SWITCH':
            session.tab_switch_count += 1
        elif activity_type == 'WINDOW_BLUR':
            session.focus_loss_count += 1
        elif activity_type == 'COPY_ATTEMPT':
            session.copy_paste_attempts += 1
        elif activity_type == 'PASTE_ATTEMPT':
            session.copy_paste_attempts += 1
        elif activity_type == 'RIGHT_CLICK':
            session.right_click_attempts += 1
        elif activity_type == 'FULLSCREEN_EXIT':
            session.was_fullscreen_exit = True
        elif activity_type == 'KEYBOARD_SHORTCUT':
            session.copy_paste_attempts += 1
        elif activity_type == 'PRINT_SCREEN':
            session.copy_paste_attempts += 1
        elif activity_type == 'SCREENSHOT_FAILED':
            # Just log, don't count as suspicious
            pass
        
        # Calculate total suspicious activities
        total_suspicious = (
            session.tab_switch_count + 
            session.focus_loss_count + 
            session.copy_paste_attempts +
            session.right_click_attempts
        )
        
        # Flag session if too many suspicious activities
        if total_suspicious >= 5:  # Adjusted threshold for testing
            session.status = 'FLAGGED'
        
        session.save()
        
        # Log the activity
        activity = SuspiciousActivity.objects.create(
            session=session,
            activity_type=activity_type,
            details=data.get('details', {})
        )
        
        return JsonResponse({
            'success': True,
            'activity_id': str(activity.activity_id),
            'session_status': session.status,
            'total_suspicious': total_suspicious
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def take_screenshot(request):
    """API to receive and save screenshots from student's browser"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        image_data = data.get('image_data')
        reason = data.get('reason', 'Scheduled capture')
        
        if not session_id or not image_data:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
        
        session = get_object_or_404(ProctoringSession, session_id=session_id)
        
        # Decode base64 image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        image_binary = base64.b64decode(image_data)
        
        # Create filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{session.student.username}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
        
        # Ensure screenshots directory exists
        screenshots_dir = os.path.join(settings.MEDIA_ROOT, 'proctoring_screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        
        filepath = os.path.join(screenshots_dir, filename)
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(image_binary)
        
        # Create relative path for database
        relative_path = os.path.join('proctoring_screenshots', filename)
        
        # Update session
        session.screenshot_count += 1
        session.save()
        
        # Create screenshot record
        screenshot = ProctoringScreenshot.objects.create(
            session=session,
            image_path=relative_path,
            reason=reason,
            is_flagged=False
        )
        
        return JsonResponse({
            'success': True,
            'screenshot_id': str(screenshot.screenshot_id),
            'filename': filename,
            'path': relative_path,
            'timestamp': str(screenshot.timestamp)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_GET
def get_screenshot(request, screenshot_id):
    """Serve a screenshot image"""
    screenshot = get_object_or_404(ProctoringScreenshot, screenshot_id=screenshot_id)
    
    # Check permission
    if request.user.role not in ['INSTRUCTOR', 'ADMIN'] and request.user != screenshot.session.student:
        return HttpResponseForbidden("Access denied")
    
    filepath = os.path.join(settings.MEDIA_ROOT, screenshot.image_path)
    
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            return HttpResponse(f.read(), content_type='image/jpeg')
    else:
        return JsonResponse({'success': False, 'error': 'Image not found'})

@csrf_exempt
@require_POST
def update_session_status(request, session_id):
    """Update proctoring session status (e.g., mark as reviewed)"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return JsonResponse({'success': False, 'error': 'Access denied'})
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in ['ACTIVE', 'COMPLETED', 'FLAGGED', 'REVIEWED']:
            return JsonResponse({'success': False, 'error': 'Invalid status'})
        
        session = get_object_or_404(ProctoringSession, session_id=session_id)
        session.status = new_status
        
        if new_status == 'COMPLETED':
            session.end_time = timezone.now()
        
        session.save()
        
        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'status': session.status,
            'end_time': str(session.end_time) if session.end_time else None
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})