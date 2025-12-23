# apps/exams/utils/plagiarism.py - UPDATED VERSION
import re
from difflib import SequenceMatcher
import hashlib
from typing import List, Dict, Tuple
# REMOVE: import requests  # We're not using this in basic version
from django.conf import settings
from django.db.models import Q

class BasicPlagiarismDetector:
    """Basic plagiarism detection using text similarity"""
    
    def __init__(self):
        self.min_similarity_threshold = 0.7  # 70% similarity
        self.min_match_length = 50  # Minimum characters to consider
    
    def clean_text(self, text: str) -> str:
        """Clean text for comparison"""
        if not text:
            return ""
        # Convert to lowercase
        text = text.lower()
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Remove punctuation (optional)
        text = re.sub(r'[^\w\s]', '', text)
        return text
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (0-1)"""
        if not text1 or not text2:
            return 0.0
        
        clean1 = self.clean_text(text1)
        clean2 = self.clean_text(text2)
        
        if not clean1 or not clean2:
            return 0.0
        
        # Use SequenceMatcher for basic similarity
        return SequenceMatcher(None, clean1, clean2).ratio()
    
    def find_matching_chunks(self, text1: str, text2: str, min_length=20) -> List[Dict]:
        """Find matching chunks between two texts"""
        matches = []
        
        if not text1 or not text2:
            return matches
        
        s = SequenceMatcher(None, text1, text2)
        
        for block in s.get_matching_blocks():
            if block.size >= min_length:
                match = {
                    'start1': block.a,
                    'end1': block.a + block.size,
                    'start2': block.b,
                    'end2': block.b + block.size,
                    'text': text1[block.a:block.a + block.size],
                    'length': block.size
                }
                matches.append(match)
        
        return matches
    
    def check_internal_plagiarism(self, answer_text: str, exam_id=None) -> Dict:
        """Check against other answers in the system"""
        from apps.exams.models import Answer
        
        results = {
            'internal_matches': [],
            'max_similarity': 0.0,
            'total_matches': 0
        }
        
        if not answer_text:
            return results
        
        # Get other answers from the same exam or all exams
        if exam_id:
            # Check against other submissions in the same exam
            other_answers = Answer.objects.filter(
                submission__exam__exam_id=exam_id
            ).exclude(answer_text='').select_related('submission__student')
        else:
            # Check against all answers (for more thorough check)
            other_answers = Answer.objects.exclude(answer_text='').select_related('submission__student')
        
        for other_answer in other_answers:
            if (other_answer.answer_text and 
                len(other_answer.answer_text) > 10 and
                other_answer.answer_text != answer_text):
                
                similarity = self.calculate_similarity(answer_text, other_answer.answer_text)
                
                if similarity >= self.min_similarity_threshold:
                    match_info = {
                        'answer_id': str(other_answer.answer_id),
                        'student': other_answer.submission.student.email,
                        'similarity': similarity,
                        'matched_chunks': self.find_matching_chunks(answer_text, other_answer.answer_text)
                    }
                    results['internal_matches'].append(match_info)
                    
                    if similarity > results['max_similarity']:
                        results['max_similarity'] = similarity
        
        results['total_matches'] = len(results['internal_matches'])
        return results
    
    def check_web_plagiarism(self, text: str) -> Dict:
        """Basic web plagiarism check (simplified version)"""
        # In a real implementation, this would call an API like Copyscape
        # For now, we'll create a simulated version
        
        results = {
            'web_matches': [],
            'total_sentences': 0,
            'suspicious_sentences': 0
        }
        
        if not text:
            return results
        
        # Split text into sentences for analysis
        sentences = re.split(r'[.!?]+', text)
        results['total_sentences'] = len(sentences)
        
        # Check for common phrases (this is a simplified version)
        common_phrases = [
            "in conclusion",
            "the purpose of this",
            "it is important to",
            "as a result",
            "on the other hand",
            "in my opinion",
            "according to",
            "for example"
        ]
        
        for i, sentence in enumerate(sentences):
            if len(sentence.strip()) > 20:  # Only check meaningful sentences
                sentence_lower = sentence.lower()
                for phrase in common_phrases:
                    if phrase in sentence_lower:
                        results['web_matches'].append({
                            'sentence_index': i,
                            'sentence': sentence.strip(),
                            'matched_phrase': phrase,
                            'similarity': 0.8  # Simulated
                        })
                        results['suspicious_sentences'] += 1
                        break
        
        return results
    
    def generate_fingerprint(self, text: str) -> str:
        """Generate a fingerprint for the text"""
        if not text:
            return ""
        # Create a simple fingerprint using hash
        clean_text = self.clean_text(text)
        return hashlib.md5(clean_text.encode()).hexdigest()
    
    def check_answer(self, answer_text: str, exam_id=None) -> Dict:
        """Run comprehensive plagiarism check"""
        if not answer_text or len(answer_text.strip()) < self.min_match_length:
            return {
                'overall_similarity': 0.0,
                'status': 'SKIPPED',
                'reason': 'Text too short'
            }
        
        results = {
            'internal': self.check_internal_plagiarism(answer_text, exam_id),
            'web': self.check_web_plagiarism(answer_text),
            'fingerprint': self.generate_fingerprint(answer_text),
            'text_length': len(answer_text)
        }
        
        # Calculate overall similarity score
        internal_max = results['internal']['max_similarity']
        web_score = results['web']['suspicious_sentences'] / max(1, results['web']['total_sentences'])
        
        results['overall_similarity'] = max(internal_max, web_score)
        
        # Determine status
        if results['overall_similarity'] >= 0.8:
            results['status'] = 'HIGH_RISK'
        elif results['overall_similarity'] >= 0.5:
            results['status'] = 'MEDIUM_RISK'
        else:
            results['status'] = 'LOW_RISK'
        
        return results