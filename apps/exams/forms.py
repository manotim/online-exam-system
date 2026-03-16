# apps/exams/forms.py
from django import forms
from .models import Course, Enrollment
from apps.users.models import CustomUser

class CourseForm(forms.ModelForm):
    """Form for creating and editing courses"""
    
    class Meta:
        model = Course
        fields = ['title', 'code', 'description', 'institution']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Introduction to Computer Science'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CS101'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the course content, objectives, etc.'
            }),
            'institution': forms.Select(attrs={
                'class': 'form-select'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Make institution not required
        self.fields['institution'].required = False
        self.fields['institution'].empty_label = "Select Institution (Optional)"
        
        # Add help texts
        self.fields['code'].help_text = 'Unique course code (e.g., CS101, MATH202)'
        
        # If user is instructor, set initial institution (optional)
        if self.user and self.user.role == 'INSTRUCTOR':
            # You could set default institution based on user's profile
            pass
    
    def clean_code(self):
        """Validate that course code is unique"""
        code = self.cleaned_data.get('code')
        
        if code:
            code = code.upper()  # Store codes in uppercase
            
            # Check if this is an edit (course has an instance)
            if self.instance and self.instance.pk:
                # For edit, exclude current course
                if Course.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError('A course with this code already exists.')
            else:
                # For new course
                if Course.objects.filter(code=code).exists():
                    raise forms.ValidationError('A course with this code already exists.')
        
        return code


class CourseFilterForm(forms.Form):
    """Form for filtering courses"""
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Search by title or code...'
    }))


class EnrollmentForm(forms.Form):
    """Form to enroll students in a course"""
    student_email = forms.EmailField(
        label="Student Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter student email'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
    
    def clean_student_email(self):
        email = self.cleaned_data.get('student_email')
        try:
            student = CustomUser.objects.get(email=email, role='STUDENT')
        except CustomUser.DoesNotExist:
            raise forms.ValidationError('No student found with this email.')
        
        # Check if already enrolled
        if Enrollment.objects.filter(student=student, course=self.course, is_active=True).exists():
            raise forms.ValidationError('This student is already enrolled in the course.')
        
        return email


class BulkEnrollmentForm(forms.Form):
    """Form for bulk enrollment via CSV or text"""
    student_emails = forms.CharField(
        label="Student Emails (one per line)",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'student1@example.com\nstudent2@example.com\nstudent3@example.com'
        })
    )