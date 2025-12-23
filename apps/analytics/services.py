# apps/analytics/services.py
import json
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Max, Min, StdDev, Q, F, Sum
from django.db.models.functions import TruncDate, TruncHour
from apps.exams.models import Exam, Submission, Answer, Question
from apps.users.models import CustomUser
import statistics
from collections import defaultdict


class PerformanceAnalytics:
    """Service for student performance analytics"""
    
    @staticmethod
    def get_student_performance(student, course=None, time_period_days=90):
        """Get comprehensive performance data for a student"""
        start_date = timezone.now() - timedelta(days=time_period_days)
        
        # Base query
        submissions = Submission.objects.filter(
            student=student,
            submitted_at__gte=start_date,
            is_graded=True
        ).select_related('exam', 'exam__course')
        
        if course:
            submissions = submissions.filter(exam__course=course)
        
        total_exams = submissions.count()
        if total_exams == 0:
            return None
        
        # Calculate statistics
        exams_data = []
        
        for submission in submissions:
            exam = submission.exam
            if exam.total_points > 0:
                percentage = (submission.total_score / exam.total_points) * 100
            else:
                percentage = 0
                
            exams_data.append({
                'exam_id': exam.exam_id,
                'title': exam.title,
                'score': float(submission.total_score),
                'total_points': float(exam.total_points),
                'percentage': float(percentage),
                'submitted_at': submission.submitted_at,
                'course': exam.course.title if exam.course else None,
                'submission_id': submission.submission_id,
            })
        
        # Sort by date
        exams_data.sort(key=lambda x: x['submitted_at'], reverse=True)
        
        # Calculate statistics
        percentages = [exam['percentage'] for exam in exams_data]
        
        # Calculate strengths and weaknesses
        strengths_weaknesses = PerformanceAnalytics._analyze_strengths_weaknesses(student, submissions)
        
        return {
            'student': {
                'id': student.id,
                'email': student.email,
                'name': student.get_full_name() or student.email,
            },
            'summary': {
                'total_exams': total_exams,
                'average_score': statistics.mean([exam['score'] for exam in exams_data]) if exams_data else 0,
                'average_percentage': statistics.mean(percentages) if percentages else 0,
                'highest_score': max([exam['score'] for exam in exams_data]) if exams_data else 0,
                'lowest_score': min([exam['score'] for exam in exams_data]) if exams_data else 0,
                'std_deviation': statistics.stdev(percentages) if len(percentages) > 1 else 0,
            },
            'exams': exams_data[:10],  # Last 10 exams
            'trend': PerformanceAnalytics._calculate_performance_trend(percentages),
            'strengths_weaknesses': strengths_weaknesses,
        }
    
    @staticmethod
    def _calculate_performance_trend(percentages):
        """Calculate performance trend (improving/declining)"""
        if len(percentages) < 2:
            return 'stable'
        
        # Simple average comparison
        first_half = percentages[:len(percentages)//2]
        second_half = percentages[len(percentages)//2:]
        
        avg_first = statistics.mean(first_half) if first_half else 0
        avg_second = statistics.mean(second_half) if second_half else 0
        
        if avg_second > avg_first + 5:
            return 'improving'
        elif avg_second < avg_first - 5:
            return 'declining'
        else:
            return 'stable'
    
    @staticmethod
    def _analyze_strengths_weaknesses(student, submissions):
        """Analyze question types student performs well/poorly on"""
        # Get all answers for these submissions
        answers = Answer.objects.filter(
            submission__in=submissions,
            points_awarded__isnull=False
        ).select_related('question')
        
        performance_by_type = defaultdict(lambda: {'total': 0, 'awarded': 0, 'count': 0})
        
        for answer in answers:
            q_type = answer.question.question_type
            performance_by_type[q_type]['total'] += answer.question.points
            performance_by_type[q_type]['awarded'] += answer.points_awarded
            performance_by_type[q_type]['count'] += 1
        
        # Calculate percentages
        results = {}
        for q_type, data in performance_by_type.items():
            if data['total'] > 0:
                percentage = (data['awarded'] / data['total']) * 100
                results[q_type] = {
                    'percentage': float(percentage),
                    'total_questions': data['count'],
                    'average_score': float(data['awarded'] / data['count']) if data['count'] > 0 else 0,
                }
        
        # Identify strengths and weaknesses
        strengths = []
        weaknesses = []
        
        for q_type, data in results.items():
            if data['percentage'] >= 80:
                strengths.append({
                    'type': q_type,
                    'percentage': data['percentage'],
                    'average_score': data['average_score']
                })
            elif data['percentage'] <= 50:
                weaknesses.append({
                    'type': q_type,
                    'percentage': data['percentage'],
                    'average_score': data['average_score']
                })
        
        return {
            'strengths': strengths,
            'weaknesses': weaknesses,
            'by_question_type': results
        }


class ExamAnalytics:
    """Service for exam-level analytics"""
    
    @staticmethod
    def get_exam_statistics(exam):
        """Get comprehensive statistics for an exam"""
        submissions = exam.submissions.filter(submitted_at__isnull=False)
        graded_submissions = submissions.filter(is_graded=True)
        
        total_students = submissions.count()
        graded_count = graded_submissions.count()
        
        if graded_count == 0:
            return {
                'exam': {
                    'id': exam.exam_id,
                    'title': exam.title,
                    'total_points': float(exam.total_points),
                    'total_questions': exam.questions.count(),
                },
                'participation': {
                    'total_students': total_students,
                    'graded_count': 0,
                    'ungraded_count': total_students,
                    'completion_rate': 0,
                },
                'stats_available': False
            }
        
        # Calculate scores
        scores = list(graded_submissions.values_list('total_score', flat=True))
        max_possible = exam.total_points
        
        # Basic statistics
        scores_float = [float(s) for s in scores]
        avg_score = statistics.mean(scores_float) if scores_float else 0
        median_score = statistics.median(scores_float) if scores_float else 0
        std_dev = statistics.stdev(scores_float) if len(scores_float) > 1 else 0
        
        # Percentages
        percentages = [(float(s) / float(max_possible)) * 100 for s in scores if max_possible > 0]
        avg_percentage = statistics.mean(percentages) if percentages else 0
        
        # Grade distribution
        grade_distribution = ExamAnalytics._calculate_grade_distribution(percentages)
        
        # Question analysis
        question_stats = ExamAnalytics._analyze_question_performance(exam)
        
        # Time analysis
        time_stats = ExamAnalytics._analyze_submission_times(submissions)
        
        return {
            'exam': {
                'id': exam.exam_id,
                'title': exam.title,
                'total_points': float(max_possible),
                'total_questions': exam.questions.count(),
            },
            'participation': {
                'total_students': total_students,
                'graded_count': graded_count,
                'ungraded_count': total_students - graded_count,
                'completion_rate': (graded_count / total_students * 100) if total_students > 0 else 0,
            },
            'scores': {
                'average_score': float(avg_score),
                'median_score': float(median_score),
                'std_deviation': float(std_dev),
                'average_percentage': float(avg_percentage),
                'highest_score': float(max(scores)) if scores else 0,
                'lowest_score': float(min(scores)) if scores else 0,
            },
            'grade_distribution': grade_distribution,
            'question_stats': question_stats,
            'time_stats': time_stats,
            'stats_available': True
        }
    
    @staticmethod
    def _calculate_grade_distribution(percentages):
        """Calculate grade distribution in letter grades"""
        bins = {
            'A': (90, 100),
            'B': (80, 89),
            'C': (70, 79),
            'D': (60, 69),
            'F': (0, 59)
        }
        
        distribution = {grade: {'count': 0, 'percentage': 0} for grade in bins}
        
        for percentage in percentages:
            for grade, (low, high) in bins.items():
                if low <= percentage <= high:
                    distribution[grade]['count'] += 1
                    break
        
        total = len(percentages)
        if total > 0:
            for grade in distribution:
                distribution[grade]['percentage'] = (distribution[grade]['count'] / total) * 100
        
        return distribution


class InstitutionalAnalytics:
    """Service for institution/course-level analytics"""
    
    @staticmethod
    def get_course_performance(course):
        """Get analytics for an entire course"""
        exams = Exam.objects.filter(
            course=course,
            is_published=True
        )
        
        total_exams = exams.count()
        total_submissions = Submission.objects.filter(exam__in=exams).count()
        total_students = course.enrollments.filter(is_active=True).count()
        
        # Get all submissions for these exams
        submissions = Submission.objects.filter(
            exam__in=exams,
            is_graded=True
        )
        
        # Calculate overall statistics
        if submissions.exists():
            scores = list(submissions.values_list('total_score', flat=True))
            scores_float = [float(s) for s in scores]
            avg_score = statistics.mean(scores_float) if scores_float else 0
        else:
            avg_score = 0
        
        # Exam-level statistics
        exam_stats = []
        for exam in exams:
            exam_submissions = exam.submissions.filter(is_graded=True)
            if exam_submissions.exists():
                exam_scores = list(exam_submissions.values_list('total_score', flat=True))
                exam_scores_float = [float(s) for s in exam_scores]
                exam_avg = statistics.mean(exam_scores_float) if exam_scores_float else 0
                exam_percentage = (exam_avg / exam.total_points) * 100 if exam.total_points > 0 else 0
                
                exam_stats.append({
                    'exam_id': exam.exam_id,
                    'title': exam.title,
                    'average_score': float(exam_avg),
                    'average_percentage': float(exam_percentage),
                    'total_students': exam_submissions.count(),
                    'date': exam.end_date,
                })
        
        # Calculate trend
        trend = 'stable'
        if len(exam_stats) >= 2:
            first_avg = exam_stats[0]['average_percentage']
            last_avg = exam_stats[-1]['average_percentage']
            if last_avg > first_avg + 5:
                trend = 'improving'
            elif last_avg < first_avg - 5:
                trend = 'declining'
        
        return {
            'course': {
                'id': course.course_id,
                'title': course.title,
                'code': course.code,
            },
            'overview': {
                'total_exams': total_exams,
                'total_submissions': total_submissions,
                'total_students': total_students,
                'average_score': float(avg_score),
                'participation_rate': (total_submissions / (total_exams * total_students)) * 100 if total_exams * total_students > 0 else 0,
            },
            'exam_performance': sorted(exam_stats, key=lambda x: x['date'], reverse=True),
            'trend': trend,
        }


class ReportingService:
    """Service for generating reports and exports"""
    
    @staticmethod
    def generate_exam_report(exam, format='json'):
        """Generate a comprehensive exam report"""
        stats = ExamAnalytics.get_exam_statistics(exam)
        
        if format == 'json':
            return json.dumps(stats, default=str, indent=2)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Exam Report', exam.title])
            writer.writerow([])
            
            # Summary section
            writer.writerow(['Summary'])
            writer.writerow(['Total Students', stats['participation']['total_students']])
            writer.writerow(['Graded Submissions', stats['participation']['graded_count']])
            writer.writerow(['Average Score', stats['scores']['average_score']])
            writer.writerow(['Average Percentage', stats['scores']['average_percentage']])
            writer.writerow([])
            
            return output.getvalue()
        
        return None