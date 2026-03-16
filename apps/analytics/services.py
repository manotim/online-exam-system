# apps/analytics/services.py
import json
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Max, Min, StdDev, Q, F, Sum
from django.db.models.functions import TruncDate, TruncHour
from apps.exams.models import Exam, Submission, Answer, Question, Course
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
        total_points_earned = 0
        total_points_possible = 0
        
        for submission in submissions:
            exam = submission.exam
            if exam.total_points > 0:
                percentage = (submission.total_score / exam.total_points) * 100
            else:
                percentage = 0
                
            total_points_earned += submission.total_score or 0
            total_points_possible += exam.total_points
            
            exams_data.append({
                'exam_id': exam.exam_id,
                'title': exam.title,
                'score': float(submission.total_score or 0),
                'total_points': float(exam.total_points),
                'percentage': float(percentage),
                'submitted_at': submission.submitted_at,
                'course': exam.course.title if exam.course else None,
                'course_code': exam.course.code if exam.course else None,
                'submission_id': submission.submission_id,
            })
        
        # Sort by date
        exams_data.sort(key=lambda x: x['submitted_at'], reverse=True)
        
        # Calculate statistics
        percentages = [exam['percentage'] for exam in exams_data]
        scores = [exam['score'] for exam in exams_data]
        
        # Calculate strengths and weaknesses
        strengths_weaknesses = PerformanceAnalytics._analyze_strengths_weaknesses(student, submissions)
        
        # Calculate performance by course
        course_performance = PerformanceAnalytics._analyze_course_performance(student, submissions)
        
        # Calculate trend data for charts
        trend_data = PerformanceAnalytics._calculate_trend_data(exams_data)
        
        # Calculate percentiles (if enough data)
        percentile = PerformanceAnalytics._calculate_percentile(student, scores)
        
        return {
            'student': {
                'id': student.id,
                'email': student.email,
                'name': student.get_full_name() or student.email,
            },
            'summary': {
                'total_exams': total_exams,
                'average_score': statistics.mean(scores) if scores else 0,
                'average_percentage': statistics.mean(percentages) if percentages else 0,
                'highest_score': max(scores) if scores else 0,
                'lowest_score': min(scores) if scores else 0,
                'std_deviation': statistics.stdev(percentages) if len(percentages) > 1 else 0,
                'total_points_earned': float(total_points_earned),
                'total_points_possible': float(total_points_possible),
                'overall_percentage': (total_points_earned / total_points_possible * 100) if total_points_possible > 0 else 0,
                'percentile': percentile,
            },
            'exams': exams_data[:15],  # Last 15 exams
            'trend': PerformanceAnalytics._calculate_performance_trend(percentages),
            'trend_data': trend_data,
            'strengths_weaknesses': strengths_weaknesses,
            'course_performance': course_performance,
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
            q_type = answer.question.get_question_type_display()
            performance_by_type[q_type]['total'] += float(answer.question.points)
            performance_by_type[q_type]['awarded'] += float(answer.points_awarded or 0)
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
                    'total_points': float(data['total']),
                    'earned_points': float(data['awarded']),
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
    
    @staticmethod
    def _analyze_course_performance(student, submissions):
        """Analyze performance by course"""
        course_data = {}
        
        for submission in submissions:
            exam = submission.exam
            if exam.course:
                course = exam.course
                if course.course_id not in course_data:
                    course_data[course.course_id] = {
                        'course': course,
                        'exams_taken': 0,
                        'total_score': 0,
                        'total_possible': 0,
                        'submissions': []
                    }
                
                course_data[course.course_id]['exams_taken'] += 1
                course_data[course.course_id]['total_score'] += float(submission.total_score or 0)
                course_data[course.course_id]['total_possible'] += float(exam.total_points)
                course_data[course.course_id]['submissions'].append(submission)
        
        # Calculate percentages
        result = []
        for data in course_data.values():
            percentage = (data['total_score'] / data['total_possible'] * 100) if data['total_possible'] > 0 else 0
            result.append({
                'course_id': data['course'].course_id,
                'code': data['course'].code,
                'title': data['course'].title,
                'exams_taken': data['exams_taken'],
                'average_percentage': float(percentage),
                'total_earned': float(data['total_score']),
                'total_possible': float(data['total_possible']),
            })
        
        return sorted(result, key=lambda x: -x['average_percentage'])
    
    @staticmethod
    def _calculate_trend_data(exams_data):
        """Prepare data for trend charts"""
        # Get last 10 exams in chronological order
        recent_exams = sorted(exams_data[:10], key=lambda x: x['submitted_at'])
        
        return {
            'labels': [exam['submitted_at'].strftime('%b %d') for exam in recent_exams],
            'scores': [exam['percentage'] for exam in recent_exams],
            'exam_titles': [exam['title'][:20] for exam in recent_exams],
        }
    
    @staticmethod
    def _calculate_percentile(student, scores):
        """Calculate student's percentile compared to all students"""
        if not scores:
            return None
        
        # Get all submissions for all students (simplified)
        all_scores = Submission.objects.filter(
            is_graded=True,
            total_score__isnull=False
        ).values_list('total_score', flat=True)
        
        if not all_scores:
            return None
        
        all_scores_list = [float(s) for s in all_scores]
        avg_score = statistics.mean(scores)
        
        # Calculate percentile
        below_count = sum(1 for s in all_scores_list if s < avg_score)
        percentile = (below_count / len(all_scores_list)) * 100
        
        return round(percentile, 1)


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
    
    @staticmethod
    def _analyze_question_performance(exam):
        """Analyze performance on each question"""
        questions = exam.questions.all()
        stats = []
        
        for question in questions:
            answers = Answer.objects.filter(
                question=question,
                submission__exam=exam,
                submission__is_graded=True
            )
            
            total_answers = answers.count()
            if total_answers == 0:
                continue
            
            correct_count = answers.filter(
                points_awarded=F('question__points')
            ).count()
            
            avg_score = answers.aggregate(avg=Avg('points_awarded'))['avg'] or 0
            
            stats.append({
                'question_id': question.question_id,
                'position': question.position,
                'text': question.question_text[:50],
                'type': question.get_question_type_display(),
                'total_answers': total_answers,
                'correct_count': correct_count,
                'correct_percentage': (correct_count / total_answers * 100) if total_answers > 0 else 0,
                'average_score': float(avg_score),
                'max_score': float(question.points),
            })
        
        return sorted(stats, key=lambda x: x['position'])
    
    @staticmethod
    def _analyze_submission_times(submissions):
        """Analyze submission timing"""
        graded = submissions.filter(is_graded=True)
        
        if not graded.exists():
            return None
        
        # Calculate time taken (if available)
        time_diffs = []
        for sub in graded:
            if sub.started_at and sub.submitted_at:
                diff = (sub.submitted_at - sub.started_at).total_seconds() / 60  # minutes
                time_diffs.append(diff)
        
        if time_diffs:
            avg_time = statistics.mean(time_diffs)
            min_time = min(time_diffs)
            max_time = max(time_diffs)
        else:
            avg_time = min_time = max_time = 0
        
        return {
            'average_time_minutes': round(avg_time, 1),
            'fastest_time_minutes': round(min_time, 1),
            'slowest_time_minutes': round(max_time, 1),
            'submissions_by_hour': ExamAnalytics._group_by_hour(graded),
        }
    
    @staticmethod
    def _group_by_hour(submissions):
        """Group submissions by hour of day"""
        hour_counts = defaultdict(int)
        for sub in submissions:
            if sub.submitted_at:
                hour = sub.submitted_at.hour
                hour_counts[hour] += 1
        
        return [{'hour': h, 'count': hour_counts[h]} for h in range(24)]


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
        total_students = course.enrollment_set.filter(is_active=True).count()
        
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
    
    @staticmethod
    def get_institution_overview():
        """Get overview of entire institution"""
        total_students = CustomUser.objects.filter(role='STUDENT').count()
        total_instructors = CustomUser.objects.filter(role='INSTRUCTOR').count()
        total_courses = Course.objects.count()
        total_exams = Exam.objects.count()
        total_submissions = Submission.objects.filter(submitted_at__isnull=False).count()
        
        # Calculate average performance
        graded_submissions = Submission.objects.filter(is_graded=True)
        if graded_submissions.exists():
            avg_score = graded_submissions.aggregate(avg=Avg('total_score'))['avg'] or 0
            avg_percentage = (avg_score / Exam.objects.aggregate(avg=Avg('total_points'))['avg']) * 100 if Exam.objects.exists() else 0
        else:
            avg_score = 0
            avg_percentage = 0
        
        return {
            'totals': {
                'students': total_students,
                'instructors': total_instructors,
                'courses': total_courses,
                'exams': total_exams,
                'submissions': total_submissions,
            },
            'averages': {
                'score': float(avg_score),
                'percentage': float(avg_percentage),
            }
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
            
            # Grade distribution
            writer.writerow(['Grade Distribution'])
            for grade, data in stats['grade_distribution'].items():
                writer.writerow([grade, data['count'], f"{data['percentage']:.1f}%"])
            writer.writerow([])
            
            return output.getvalue()
        
        return None
    
    @staticmethod
    def generate_student_report(student, course=None, format='json'):
        """Generate a comprehensive student report"""
        performance = PerformanceAnalytics.get_student_performance(
            student, 
            course=course
        )
        
        if format == 'json':
            return json.dumps(performance, default=str, indent=2)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Student Performance Report', student.email])
            writer.writerow([])
            
            if performance:
                # Summary
                writer.writerow(['Summary'])
                writer.writerow(['Total Exams', performance['summary']['total_exams']])
                writer.writerow(['Average Percentage', f"{performance['summary']['average_percentage']:.1f}%"])
                writer.writerow(['Overall Percentage', f"{performance['summary']['overall_percentage']:.1f}%"])
                writer.writerow([])
                
                # Exam History
                writer.writerow(['Exam History'])
                writer.writerow(['Exam', 'Score', 'Percentage', 'Date'])
                for exam in performance['exams']:
                    writer.writerow([
                        exam['title'],
                        f"{exam['score']}/{exam['total_points']}",
                        f"{exam['percentage']:.1f}%",
                        exam['submitted_at'].strftime('%Y-%m-%d')
                    ])
            
            return output.getvalue()
        
        return None