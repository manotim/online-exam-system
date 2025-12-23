# apps/exams/management/commands/seed_data.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import Institution, CustomUser
from apps.exams.models import Course, Exam, Question
import uuid
from datetime import timedelta

class Command(BaseCommand):
    help = 'Seed initial data for the exam system'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding initial data...')
        
        # Create Institution
        institution, created = Institution.objects.get_or_create(
            name='Test University',
            domain='testuniversity.edu'
        )
        
        # Create Admin User (if not exists)
        admin_user, created = CustomUser.objects.get_or_create(
            email='admin@testuniversity.edu',
            defaults={
                'username': 'admin',
                'role': 'ADMIN',
                'institution': institution,
                'is_staff': True,
                'is_superuser': True
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()
        
        # Create Instructor
        instructor, created = CustomUser.objects.get_or_create(
            email='instructor@testuniversity.edu',
            defaults={
                'username': 'instructor',
                'role': 'INSTRUCTOR',
                'institution': institution
            }
        )
        instructor.set_password('instructor123')
        instructor.save()
        
        # Create Student
        student, created = CustomUser.objects.get_or_create(
            email='student@testuniversity.edu',
            defaults={
                'username': 'student',
                'role': 'STUDENT',
                'institution': institution
            }
        )
        student.set_password('student123')
        student.save()
        
        # Create Course
        course, created = Course.objects.get_or_create(
            code='CS101',
            defaults={
                'title': 'Introduction to Computer Science',
                'description': 'Basic concepts of computer science and programming',
                'instructor': instructor,
                'institution': institution
            }
        )
        
        # Create Exam
        exam, created = Exam.objects.get_or_create(
            title='Midterm Exam',
            defaults={
                'description': 'Midterm examination covering chapters 1-5',
                'instructor': instructor,
                'course': course,
                'time_limit_minutes': 120,
                'total_points': 100,
                'passing_score': 60,
                'start_date': timezone.now() + timedelta(days=1),
                'end_date': timezone.now() + timedelta(days=7),
                'is_published': True
            }
        )
        
        # Create Questions
        questions_data = [
            {
                'question_type': 'MCQ',
                'question_text': 'What does CPU stand for?',
                'points': 10,
                'options': ['Central Processing Unit', 'Computer Personal Unit', 'Central Processor Unit', 'Computer Processing Unit'],
                'correct_answer': 'Central Processing Unit'
            },
            {
                'question_type': 'TRUE_FALSE',
                'question_text': 'Python is a compiled language.',
                'points': 5,
                'correct_answer': 'False'
            },
            {
                'question_type': 'SHORT_ANSWER',
                'question_text': 'What is the time complexity of binary search?',
                'points': 15,
                'correct_answer': 'O(log n)'
            }
        ]
        
        for i, q_data in enumerate(questions_data, 1):
            Question.objects.get_or_create(
                exam=exam,
                position=i,
                defaults=q_data
            )
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded initial data!'))
        self.stdout.write('Test Credentials:')
        self.stdout.write(f'  Admin: admin@testuniversity.edu / admin123')
        self.stdout.write(f'  Instructor: instructor@testuniversity.edu / instructor123')
        self.stdout.write(f'  Student: student@testuniversity.edu / student123')