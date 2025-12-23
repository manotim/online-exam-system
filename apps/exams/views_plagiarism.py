# apps/exams/views_plagiarism.py - UPDATED VERSION
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Answer, PlagiarismCheck, Exam, Submission, PlagiarismSource
from .utils.plagiarism import BasicPlagiarismDetector

@login_required
def plagiarism_dashboard(request):
    """Plagiarism detection dashboard for instructors"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return HttpResponseForbidden("Access denied")
    
    # Get instructor's exams
    exams = Exam.objects.filter(instructor=request.user)
    
    # Get answers that need plagiarism checking
    answers_to_check = Answer.objects.filter(
        submission__exam__in=exams,
        question__question_type__in=['ESSAY', 'SHORT_ANSWER'],
        answer_text__isnull=False
    ).exclude(answer_text='').select_related(
        'submission', 'submission__student', 'question'
    )
    
    # Get completed plagiarism checks
    plagiarism_checks = PlagiarismCheck.objects.filter(
        answer__submission__exam__in=exams
    ).select_related(
        'answer', 'answer__submission', 'answer__submission__student'
    ).order_by('-checked_at')
    
    context = {
        'exams': exams,
        'answers_to_check': answers_to_check,
        'plagiarism_checks': plagiarism_checks,
        'high_risk_count': plagiarism_checks.filter(similarity_score__gte=0.8).count(),
        'medium_risk_count': plagiarism_checks.filter(
            similarity_score__gte=0.5, similarity_score__lt=0.8
        ).count(),
    }
    return render(request, 'exams/plagiarism_dashboard.html', context)

@login_required
@require_POST
def run_plagiarism_check(request, answer_id):
    """Run plagiarism check on a specific answer"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return JsonResponse({'success': False, 'error': 'Access denied'})
    
    answer = get_object_or_404(Answer, answer_id=answer_id)
    
    # Check permission
    if answer.submission.exam.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    # Check if already being processed
    existing_check = PlagiarismCheck.objects.filter(answer=answer).first()
    if existing_check and existing_check.status == 'PROCESSING':
        return JsonResponse({'success': False, 'error': 'Check already in progress'})
    
    # Create plagiarism check record
    plagiarism_check = PlagiarismCheck.objects.create(
        answer=answer,
        status='PROCESSING'
    )
    
    try:
        # Run plagiarism detection
        detector = BasicPlagiarismDetector()
        results = detector.check_answer(
            answer.answer_text,
            exam_id=answer.submission.exam.exam_id
        )
        
        # Update check record
        plagiarism_check.similarity_score = results.get('overall_similarity', 0)
        plagiarism_check.status = 'COMPLETED'
        plagiarism_check.completed_at = timezone.now()
        plagiarism_check.report = results
        
        # Count sources found
        internal_matches = len(results.get('internal', {}).get('internal_matches', []))
        web_matches = len(results.get('web', {}).get('web_matches', []))
        plagiarism_check.sources_found = internal_matches + web_matches
        
        plagiarism_check.save()
        
        # Create source records - UPDATED FIELD NAME
        if 'internal' in results:
            for match in results['internal'].get('internal_matches', []):
                matched_text = ''
                if match.get('matched_chunks'):
                    matched_text = match['matched_chunks'][0].get('text', '') if match['matched_chunks'] else ''
                
                PlagiarismSource.objects.create(
                    plagiarism_check=plagiarism_check,  # Changed from check=
                    source_type='INTERNAL',
                    similarity=match['similarity'],
                    source_name=f"Student: {match['student']}",
                    matched_text=matched_text,
                    source_text=match.get('matched_text', '')
                )
        
        if 'web' in results:
            for match in results['web'].get('web_matches', []):
                PlagiarismSource.objects.create(
                    plagiarism_check=plagiarism_check,  # Changed from check=
                    source_type='WEB',
                    similarity=match['similarity'],
                    source_name="Common phrase match",
                    matched_text=match['sentence'],
                    source_text=match['matched_phrase']
                )
        
        return JsonResponse({
            'success': True,
            'check_id': str(plagiarism_check.check_id),
            'similarity_score': plagiarism_check.similarity_score,
            'sources_found': plagiarism_check.sources_found
        })
        
    except Exception as e:
        plagiarism_check.status = 'FAILED'
        plagiarism_check.save()
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def plagiarism_check_detail(request, check_id):
    """View detailed plagiarism check results"""
    plagiarism_check = get_object_or_404(
        PlagiarismCheck.objects.select_related(
            'answer',
            'answer__submission',
            'answer__submission__student',
            'answer__question'
        ),
        check_id=check_id
    )
    
    # Check permission
    if (plagiarism_check.answer.submission.exam.instructor != request.user and 
        request.user.role != 'ADMIN'):
        return HttpResponseForbidden("Access denied")
    
    sources = plagiarism_check.sources.all()  # This uses related_name='sources'
    
    context = {
        'check': plagiarism_check,
        'sources': sources,
        'answer': plagiarism_check.answer,
        'student': plagiarism_check.answer.submission.student,
        'exam': plagiarism_check.answer.submission.exam
    }
    return render(request, 'exams/plagiarism_check_detail.html', context)

@login_required
@require_POST
def bulk_plagiarism_check(request, exam_id):
    """Run plagiarism checks on all answers in an exam"""
    if request.user.role not in ['INSTRUCTOR', 'ADMIN']:
        return JsonResponse({'success': False, 'error': 'Access denied'})
    
    exam = get_object_or_404(Exam, exam_id=exam_id)
    
    # Check permission
    if exam.instructor != request.user and request.user.role != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    # Get all essay/short answer answers for this exam
    answers = Answer.objects.filter(
        submission__exam=exam,
        question__question_type__in=['ESSAY', 'SHORT_ANSWER'],
        answer_text__isnull=False
    ).exclude(answer_text='')
    
    check_ids = []
    for answer in answers:
        # Check if already checked
        if not PlagiarismCheck.objects.filter(answer=answer, status='COMPLETED').exists():
            # Create and run check
            plagiarism_check = PlagiarismCheck.objects.create(
                answer=answer,
                status='PENDING'
            )
            check_ids.append(str(plagiarism_check.check_id))
    
    return JsonResponse({
        'success': True,
        'message': f'Scheduled {len(check_ids)} plagiarism checks',
        'check_ids': check_ids,
        'total_answers': answers.count()
    })