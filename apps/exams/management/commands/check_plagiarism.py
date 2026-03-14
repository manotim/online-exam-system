# management/commands/check_plagiarism.py
from django.core.management.base import BaseCommand
from apps.exams.models import Exam, Answer, PlagiarismCheck
from apps.exams.utils.plagiarism import BasicPlagiarismDetector
from django.utils import timezone

class Command(BaseCommand):
    help = 'Run plagiarism checks on all answers in an exam'
    
    def add_arguments(self, parser):
        parser.add_argument('exam_id', type=str, help='Exam ID to check')
        parser.add_argument('--threshold', type=float, default=0.7, help='Similarity threshold')
    
    def handle(self, *args, **options):
        exam_id = options['exam_id']
        threshold = options['threshold']
        
        try:
            exam = Exam.objects.get(exam_id=exam_id)
        except Exam.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Exam {exam_id} not found'))
            return
        
        answers = Answer.objects.filter(
            submission__exam=exam,
            question__question_type__in=['ESSAY', 'SHORT_ANSWER']
        ).exclude(answer_text='')
        
        detector = BasicPlagiarismDetector(similarity_threshold=threshold)
        
        for answer in answers:
            # Check if already checked
            if PlagiarismCheck.objects.filter(answer=answer, status='COMPLETED').exists():
                continue
            
            check = PlagiarismCheck.objects.create(
                answer=answer,
                status='PROCESSING'
            )
            
            try:
                peer_matches = detector.check_against_other_students(answer, exam_id)
                
                # Save results
                check.status = 'COMPLETED'
                check.completed_at = timezone.now()
                check.similarity_score = max([m['similarity'] for m in peer_matches.get('matches', [])]) if peer_matches.get('matches') else 0
                check.sources_found = len(peer_matches.get('matches', []))
                check.save()
                
                # Create source records
                for match in peer_matches.get('matches', []):
                    # Create source record logic here
                    pass
                    
            except Exception as e:
                check.status = 'FAILED'
                check.save()
                self.stdout.write(self.style.ERROR(f'Error checking answer {answer.answer_id}: {e}'))
        
        self.stdout.write(self.style.SUCCESS(f'Completed plagiarism checks for exam {exam.title}'))