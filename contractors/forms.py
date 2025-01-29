from django import forms
from .models import Tutorials

class TutorialForm(forms.ModelForm):
    class Meta:
        model = Tutorials
        fields = ['title', 'description', 'video', 'thumbnail']