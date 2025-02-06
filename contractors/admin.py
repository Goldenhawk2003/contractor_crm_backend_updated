from django.contrib import admin
from .models import User, Contractor, Contract
from .models import Client, Review, Quiz, FormResponse, Invoice, Payment, CustomOutstandingToken, Tutorials, Blog
from django import forms
from django.contrib import admin

class ClientAdminForm(forms.ModelForm):
    user = forms.ModelChoiceField(queryset=User.objects.all())

    class Meta:
        model = Client
        fields = '__all__'

class ClientAdmin(admin.ModelAdmin):
    form = ClientAdminForm
    list_display = ('user',  )  # Customize display as needed

    def save_model(self, request, obj, form, change):
        if obj.user:  # Ensuring a User is selected
            super().save_model(request, obj, form, change)
        else:
            self.message_user(request, "A valid User must be selected for a Client.", level='error')


class QuizAdmin(admin.ModelAdmin):
    list_display = ['question', 'question_type']
    search_fields = ['question']
    list_filter = ['question_type']


class FormResponseAdmin(admin.ModelAdmin):
    list_display = ['client', 'quiz', 'answer', 'selected_choice', 'created_at']
    search_fields = ['client__username', 'quiz__question']
    list_filter = ['created_at']

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('title', 'sent_at')
    search_fields = ('title',)

admin.site.register(Blog)
admin.site.register(Tutorials)
admin.site.register(Client, ClientAdmin)
admin.site.register(User)
admin.site.register(Contractor)
admin.site.register(Review)
admin.site.register(Quiz)
admin.site.register(FormResponse)
admin.site.register(Invoice)
admin.site.register(Payment)
