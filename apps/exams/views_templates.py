# apps/exams/views_templates.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.contrib import messages
from .models import ExamTemplate, TemplateQuestion, Exam, Question, Course
import json

@login_required
def template_list(request):
    """List all exam templates for the instructor"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    # Get instructor's templates
    templates = ExamTemplate.objects.filter(instructor=request.user)
    
    # Get public templates from other instructors
    public_templates = ExamTemplate.objects.filter(is_public=True).exclude(instructor=request.user)
    
    context = {
        'templates': templates,
        'public_templates': public_templates,
        'courses': Course.objects.filter(instructor=request.user)
    }
    return render(request, 'exams/template_list.html', context)

@login_required
def template_create(request):
    """Create a new exam template"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        course_id = request.POST.get('course')
        
        if not name:
            messages.error(request, "Template name is required")
            return redirect('exams:template_create')
        
        course = None
        if course_id:
            course = get_object_or_404(Course, course_id=course_id)
        
        template = ExamTemplate.objects.create(
            name=name,
            description=description,
            instructor=request.user,
            course=course,
            default_time_limit=request.POST.get('default_time_limit'),
            default_total_points=request.POST.get('default_total_points', 100),
            require_secure_browser=request.POST.get('require_secure_browser') == 'on',
            enable_plagiarism_check=request.POST.get('enable_plagiarism_check') == 'on',
            is_public=request.POST.get('is_public') == 'on'
        )
        
        messages.success(request, f"Template '{template.name}' created successfully")
        return redirect('exams:template_edit', template_id=template.template_id)
    
    context = {
        'courses': Course.objects.filter(instructor=request.user)
    }
    return render(request, 'exams/template_create.html', context)

@login_required
def template_detail(request, template_id):
    """View template details"""
    template = get_object_or_404(
        ExamTemplate.objects.select_related('instructor', 'course'),
        template_id=template_id
    )
    
    # Check permission
    if not template.is_public and template.instructor != request.user and request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    
    questions = template.template_questions.all().order_by('position')
    
    context = {
        'template': template,
        'questions': questions,
        'can_edit': template.instructor == request.user or request.user.role == 'ADMIN'
    }
    return render(request, 'exams/template_detail.html', context)

@login_required
def template_edit(request, template_id):
    """Edit an exam template"""
    template = get_object_or_404(ExamTemplate, template_id=template_id)
    
    # Check permission
    if template.instructor != request.user and request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    
    if request.method == 'POST':
        template.name = request.POST.get('name', template.name)
        template.description = request.POST.get('description', template.description)
        
        course_id = request.POST.get('course')
        if course_id:
            template.course = get_object_or_404(Course, course_id=course_id)
        else:
            template.course = None
        
        template.default_time_limit = request.POST.get('default_time_limit') or None
        template.default_total_points = request.POST.get('default_total_points', 100)
        template.require_secure_browser = request.POST.get('require_secure_browser') == 'on'
        template.enable_plagiarism_check = request.POST.get('enable_plagiarism_check') == 'on'
        template.is_public = request.POST.get('is_public') == 'on'
        
        template.save()
        messages.success(request, "Template updated successfully")
        return redirect('exams:template_detail', template_id=template.template_id)
    
    questions = template.template_questions.all().order_by('position')
    
    context = {
        'template': template,
        'questions': questions,
        'courses': Course.objects.filter(instructor=request.user)
    }
    return render(request, 'exams/template_edit.html', context)

@login_required
@require_POST
def template_delete(request, template_id):
    """Delete an exam template"""
    template = get_object_or_404(ExamTemplate, template_id=template_id)
    
    # Check permission
    if template.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    template_name = template.name
    template.delete()
    
    messages.success(request, f"Template '{template_name}' deleted successfully")
    return JsonResponse({'success': True})

@login_required
@require_POST
def template_create_exam(request, template_id):
    """Create an exam from a template"""
    template = get_object_or_404(
        ExamTemplate.objects.select_related('course'),
        template_id=template_id
    )
    
    # Check permission for private templates
    if not template.is_public and template.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    data = json.loads(request.body)
    exam_title = data.get('title')
    exam_description = data.get('description', '')
    
    if not exam_title:
        return JsonResponse({'success': False, 'error': 'Exam title is required'})
    
    # Create exam from template
    exam = Exam.objects.create(
        title=exam_title,
        description=exam_description or template.description,
        instructor=request.user,
        course=template.course,
        time_limit_minutes=template.default_time_limit,
        total_points=template.default_total_points,
        require_secure_browser=template.require_secure_browser,
        enable_plagiarism_check=template.enable_plagiarism_check,
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=7),  # Default 7 days from now
        is_published=False
    )
    
    # Copy questions from template
    template_questions = template.template_questions.all().order_by('position')
    for tq in template_questions:
        Question.objects.create(
            exam=exam,
            question_type=tq.question_type,
            question_text=tq.question_text,
            points=tq.points,
            correct_answer=tq.correct_answer,
            options=tq.options,
            position=tq.position,
            rubric=tq.rubric,
            expected_answer_length=tq.expected_answer_length
        )
    
    # Update template usage count
    template.usage_count += 1
    template.save()
    
    return JsonResponse({
        'success': True,
        'exam_id': str(exam.exam_id),
        'exam_title': exam.title,
        'questions_added': template_questions.count()
    })

@login_required
@require_POST
def template_add_question(request, template_id):
    """Add a question to a template"""
    template = get_object_or_404(ExamTemplate, template_id=template_id)
    
    # Check permission
    if template.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    data = json.loads(request.body)
    
    # Get the highest position
    max_position = TemplateQuestion.objects.filter(template=template).aggregate(models.Max('position'))['position__max'] or 0
    
    question = TemplateQuestion.objects.create(
        template=template,
        question_type=data.get('question_type', 'MCQ'),
        question_text=data.get('question_text', ''),
        points=data.get('points', 1),
        correct_answer=data.get('correct_answer', ''),
        options=data.get('options', []),
        instructions=data.get('instructions', ''),
        expected_answer_length=data.get('expected_answer_length'),
        position=max_position + 1
    )
    
    return JsonResponse({
        'success': True,
        'question_id': str(question.template_question_id),
        'question_text': question.question_text[:50] + '...' if len(question.question_text) > 50 else question.question_text
    })

@login_required
@require_POST
def template_delete_question(request, question_id):
    """Delete a question from a template"""
    question = get_object_or_404(TemplateQuestion, template_question_id=question_id)
    
    # Check permission
    if question.template.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    question.delete()
    
    # Reorder remaining questions
    remaining_questions = TemplateQuestion.objects.filter(template=question.template).order_by('position')
    for index, q in enumerate(remaining_questions, start=1):
        q.position = index
        q.save()
    
    return JsonResponse({'success': True})