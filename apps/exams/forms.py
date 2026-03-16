# apps/exams/forms.py
from django import forms
from .models import Course

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