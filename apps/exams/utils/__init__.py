# apps/exams/utils/__init__.py
from .exam_utils import (
    can_access_exam,
    validate_exam_timing,
    prepare_exam_context,
    calculate_time_remaining,
    check_answer_plagiarism
)
from .plagiarism import BasicPlagiarismDetector