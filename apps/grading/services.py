# apps/grading/services.py
import json
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, StdDev, Max, Min, Count
from apps.exams.models import Answer, Submission
from apps.grading.models import Rubric, RubricCriterion, GradeDistribution, GradingSession


class AutoGradingService:
    """Service for automatic grading of objective questions"""
    
    @staticmethod
    def grade_mcq(answer, question):
        """Grade multiple choice questions"""
        student_answer = answer.answer_text.strip()
        correct_answer = question.correct_answer.strip()
        
        # Direct comparison
        if student_answer == correct_answer:
            return Decimal(str(question.points))
        return Decimal('0.0')
    
    @staticmethod
    def grade_true_false(answer, question):
        """Grade true/false questions"""
        student_answer = answer.answer_text.lower().strip()
        correct_answer = question.correct_answer.lower().strip()
        
        if student_answer == correct_answer:
            return Decimal(str(question.points))
        return Decimal('0.0')
    
    @staticmethod
    def grade_with_rubric(answer, rubric_scores):
        """
        Grade using rubric scores.
        rubric_scores: dict of {criterion_id: score}
        """
        if not answer.question.rubric:
            return Decimal('0.0')
        
        total_score = Decimal('0.0')
        rubric = answer.question.rubric
        
        for criterion in rubric.criteria.all():
            criterion_id = str(criterion.criterion_id)
            if criterion_id in rubric_scores:
                score = Decimal(str(rubric_scores[criterion_id]))
                if 0 <= score <= criterion.max_score:
                    weighted_score = score * criterion.weight
                    total_score += weighted_score
        
        # Cap at question points
        max_points = answer.question.points
        return min(total_score, max_points)
    
    @staticmethod
    def auto_grade_submission(submission, save=True):
        """
        Auto-grade all auto-gradeable answers in a submission.
        Returns total points awarded.
        """
        total_score = Decimal('0.0')
        
        with transaction.atomic():
            for answer in submission.answers.all():
                if answer.points_awarded is not None:
                    # Already graded
                    total_score += answer.points_awarded
                    continue
                
                question = answer.question
                
                if question.question_type == 'MCQ':
                    points = AutoGradingService.grade_mcq(answer, question)
                    if save:
                        answer.points_awarded = points
                        answer.save()
                    total_score += points
                    
                elif question.question_type == 'TRUE_FALSE':
                    points = AutoGradingService.grade_true_false(answer, question)
                    if save:
                        answer.points_awarded = points
                        answer.save()
                    total_score += points
                
                # Note: Short Answer and Essay require manual grading
        
        return total_score
    
    @staticmethod
    def update_submission_status(submission):
        """Update submission grading status based on answers"""
        total_questions = submission.exam.questions.count()
        graded_answers = submission.answers.filter(points_awarded__isnull=False).count()
        auto_graded = submission.answers.filter(
            points_awarded__isnull=False,
            grader__isnull=True
        ).count()
        manually_graded = submission.answers.filter(
            points_awarded__isnull=False,
            grader__isnull=False
        ).count()
        
        if total_questions == 0:
            submission.grading_status = 'PENDING'
        elif graded_answers == total_questions:
            if manually_graded > 0:
                submission.grading_status = 'MANUALLY_GRADED'
                submission.is_graded = True
            else:
                submission.grading_status = 'AUTO_GRADED'
                submission.is_graded = True
        elif graded_answers > 0:
            submission.grading_status = 'PARTIALLY_GRADED'
            submission.is_graded = False
        else:
            submission.grading_status = 'PENDING'
            submission.is_graded = False
        
        # Update total score
        total_score = Decimal('0.0')
        for answer in submission.answers.filter(points_awarded__isnull=False):
            total_score += answer.points_awarded
        
        submission.total_score = total_score
        submission.save()
        
        return submission.grading_status


class RubricGradingService:
    """Service for rubric-based grading"""
    
    @staticmethod
    def create_rubric_from_template(template_name, instructor, questions=None):
        """Create rubric from predefined template"""
        templates = {
            'analytic_essay': {
                'name': 'Analytic Essay Rubric',
                'type': 'ANALYTIC',
                'max_score': 10,
                'criteria': [
                    {'title': 'Thesis', 'max_score': 3, 'weight': 1.0},
                    {'title': 'Evidence', 'max_score': 3, 'weight': 1.0},
                    {'title': 'Organization', 'max_score': 2, 'weight': 1.0},
                    {'title': 'Grammar', 'max_score': 2, 'weight': 1.0},
                ]
            },
            'holistic_essay': {
                'name': 'Holistic Essay Rubric',
                'type': 'HOLISTIC',
                'max_score': 10,
                'criteria': [
                    {'title': 'Overall Quality', 'max_score': 10, 'weight': 1.0},
                ]
            },
        }
        
        if template_name not in templates:
            return None
        
        template = templates[template_name]
        
        rubric = Rubric.objects.create(
            name=template['name'],
            rubric_type=template['type'],
            max_score=template['max_score'],
            instructor=instructor,
            is_public=True
        )
        
        for i, criterion_data in enumerate(template['criteria']):
            RubricCriterion.objects.create(
                rubric=rubric,
                title=criterion_data['title'],
                max_score=criterion_data['max_score'],
                weight=criterion_data.get('weight', 1.0),
                order=i
            )
        
        # Attach to questions if provided
        if questions:
            for question in questions:
                question.rubric = rubric
                question.save()
        
        return rubric
    
    @staticmethod
    def apply_rubric_to_answer(answer, rubric_scores, grader, feedback=""):
        """Apply rubric scores to an answer"""
        if not answer.question.rubric:
            raise ValueError("Question has no rubric assigned")
        
        # Calculate total score using AutoGradingService
        total_score = AutoGradingService.grade_with_rubric(answer, rubric_scores)
        
        # Update answer
        answer.points_awarded = total_score
        answer.rubric_scores = rubric_scores
        answer.grader = grader
        answer.graded_at = timezone.now()
        answer.manual_feedback = feedback
        
        # Save and return
        answer.save()
        return total_score


class AnalyticsService:
    """Service for grading analytics and statistics"""
    
    @staticmethod
    def calculate_grade_distribution(exam, question=None):
        """Calculate grade distribution for an exam or question"""
        if question:
            # Question-level distribution
            scores = list(Answer.objects.filter(
                question=question,
                points_awarded__isnull=False
            ).values_list('points_awarded', flat=True))
        else:
            # Exam-level distribution
            scores = list(Submission.objects.filter(
                exam=exam,
                total_score__isnull=False
            ).values_list('total_score', flat=True))
        
        if not scores:
            return None
        
        # Convert to float for calculations
        scores_float = [float(score) for score in scores]
        
        import statistics
        from decimal import Decimal
        
        avg = statistics.mean(scores_float) if scores_float else 0
        median = statistics.median(scores_float) if scores_float else 0
        std_dev = statistics.stdev(scores_float) if len(scores_float) > 1 else 0
        
        # Create or update distribution
        distribution, created = GradeDistribution.objects.update_or_create(
            exam=exam,
            question=question,
            defaults={
                'scores': scores,
                'average_score': Decimal(str(avg)),
                'median_score': Decimal(str(median)),
                'standard_deviation': Decimal(str(std_dev))
            }
        )
        
        return distribution
    
    @staticmethod
    def get_grading_efficiency(instructor, days=30):
        """Calculate grading efficiency for an instructor"""
        from django.db.models import Sum, Avg
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        sessions = GradingSession.objects.filter(
            instructor=instructor,
            start_time__gte=start_date,
            status='COMPLETED'
        )
        
        if not sessions.exists():
            return {
                'total_sessions': 0,
                'total_submissions': 0,
                'avg_time_per_submission': 0,
                'efficiency_score': 0
            }
        
        total_sessions = sessions.count()
        total_submissions = sessions.aggregate(
            total=Sum('submissions_graded')
        )['total'] or 0
        
        avg_time = sessions.aggregate(
            avg_time=Avg('average_time_per_submission')
        )['avg_time'] or 0
        
        # Calculate efficiency score (submissions per hour)
        efficiency_score = 0
        if avg_time > 0:
            submissions_per_hour = (60 * 60) / avg_time
            efficiency_score = min(100, submissions_per_hour * 10)  # Scale to 0-100
        
        return {
            'total_sessions': total_sessions,
            'total_submissions': total_submissions,
            'avg_time_per_submission': avg_time,
            'efficiency_score': efficiency_score
        }


class NotificationService:
    """Service for grade publishing notifications"""
    
    @staticmethod
    def publish_grades(submission):
        """Publish grades for a submission and notify student"""
        # Update submission
        submission.is_graded = True
        submission.save()
        
        # Send notification (simplified - you can integrate with email or websockets)
        student = submission.student
        exam = submission.exam
        
        notification = {
            'type': 'GRADE_PUBLISHED',
            'student_email': student.email,
            'exam_title': exam.title,
            'score': float(submission.total_score),
            'total_points': float(exam.total_points),
            'percentage': float((submission.total_score / exam.total_points) * 100) if exam.total_points > 0 else 0,
            'timestamp': timezone.now().isoformat()
        }
        
        # In a real app, you would:
        # 1. Save to database
        # 2. Send email
        # 3. Send websocket notification
        
        return notification
    
    @staticmethod
    def bulk_publish_grades(exam):
        """Publish grades for all submissions in an exam"""
        submissions = Submission.objects.filter(
            exam=exam,
            is_graded=True  # Only publish already graded submissions
        )
        
        notifications = []
        for submission in submissions:
            notification = NotificationService.publish_grades(submission)
            notifications.append(notification)
        
        return {
            'exam': exam.title,
            'total_published': len(notifications),
            'notifications': notifications
        }