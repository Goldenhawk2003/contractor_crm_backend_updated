from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework_simplejwt.tokens import OutstandingToken
# Create your models here.

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('client', 'Client'),
        ('professional', 'Professional'),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    profession = models.CharField(max_length=100, blank=True, null=True)  # For contractors only

    # Add related_name to resolve clashes
    groups = models.ManyToManyField(Group, related_name='contractors_user_groups')
    user_permissions = models.ManyToManyField(Permission, related_name='contractors_user_permissions')

# Contractor model linked to User
class Contractor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='contractor_profile')
    job_type = models.CharField(max_length=100)
    experience_years = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    profile_description = models.TextField(blank=True, null=True)
    picture = models.ImageField(upload_to='contractor_pictures/', blank=True, null=True)  # Optional picture
    location = models.CharField(max_length=255, blank=True, null=True)  # Optional location

    
    def __str__(self):
        return self.user.username


# Contract model between client and contractor
class Contract(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_contracts')
    contractor = models.ForeignKey(Contractor, on_delete=models.CASCADE, related_name='contractor_contracts')
    details = models.TextField()
    signed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default='Pending')  # Example statuses: Pending, Signed, Completed
    
    def __str__(self):
        return f"Contract between {self.client.username} and {self.contractor.user.username}"
    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(status='Completed', signed_at__isnull=False), name='completed_contract_must_be_signed')
        ]
    
class Client(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    company_name = models.CharField(max_length=100, blank=True, null=True)
    
class Review(models.Model):
    contractor = models.ForeignKey(Contractor, on_delete=models.CASCADE, related_name='reviews')
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_reviews')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])  # Rating between 1 and 5, for example
    review_text = models.TextField(blank=True)  # Optional review text
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp for when the review was created

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['contractor', 'client'], name='unique_review_per_client_contractor')
        ]

    def __str__(self):
        return f"Review by {self.client.username} for {self.contractor.user.username}"
    
    def save(self, *args, **kwargs):
        if not (1 <= self.rating <= 5):
            raise ValueError("Rating must be between 1 and 5.")
        super(Review, self).save(*args, **kwargs)

class Quiz(models.Model):
    QUESTION_TYPES = [
        ('text', 'Text Answer'),  # Open-ended text-based question
        ('multiple_choice', 'Multiple Choice'),
    ]
    question = models.CharField(max_length=255)  # Question text
    description = models.TextField(blank=True, null=True)  # Optional description for the question
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='text')  # Text or Multiple Choice
    choices = models.JSONField(blank=True, null=True)  # Stores multiple-choice options as a JSON array

    def __str__(self):
        return self.question

    def is_multiple_choice(self):
        """Check if the question is multiple-choice."""
        return self.question_type == 'multiple_choice'
    

class FormResponse(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='form_responses')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='responses')
    answer = models.CharField(max_length=255, blank=True, null=True)  # Client's answer for text-based questions
    selected_choice = models.CharField(max_length=255, blank=True, null=True)  # For multiple-choice questions
    contractor_suggestion = models.ForeignKey('Contractor', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp when the response was created

    def __str__(self):
        if self.selected_choice:
            return f"{self.client.username} selected '{self.selected_choice}' for '{self.quiz.question}'"
        return f"{self.client.username} answered '{self.answer}' for '{self.quiz.question}'"
    
class Invoice(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='invoices')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, default=1)
    contractor = models.ForeignKey(Contractor, on_delete=models.CASCADE, default= 1)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()  # The date by which payment is due
    status = models.CharField(max_length=50, default='Unpaid')  # e.g., 'Paid', 'Unpaid', 'Overdue'

    def __str__(self):
        return f"Invoice #{self.id} for Contract #{self.contract.id}"

    @property
    def is_overdue(self):
        from django.utils.timezone import now
        return self.status == 'Unpaid' and self.due_date < now()
    
class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments', default=1)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    payment_method = models.CharField(max_length=50, choices=[('Credit Card', 'Credit Card'), ('PayPal', 'PayPal'), ('Bank Transfer', 'Bank Transfer')])

    def __str__(self):
        return f"Payment of {self.payment_amount} for Invoice #{self.invoice.id}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Check if the invoice is fully paid
        total_paid = sum(payment.payment_amount for payment in self.invoice.payments.all())
        if total_paid >= self.invoice.amount_due:
            self.invoice.status = 'Paid'
            Contract.status = 'completed'
        else:
            self.invoice.status = 'Partially Paid'
        self.invoice.save()

class QuizQuestion(models.Model):
    question_text = models.CharField(max_length=255)
    job_type_association = models.CharField(max_length=100)  # This ties to the contractor's job type, e.g., 'Plumbing'

    def __str__(self):
        return self.question_text

class QuizAnswer(models.Model):
    question = models.ForeignKey(QuizQuestion, related_name='answers', on_delete=models.CASCADE)
    answer_text = models.CharField(max_length=255)
    job_type = models.CharField(max_length=100)  # This answer is tied to a job type

    def __str__(self):
        return f"Answer: {self.answer_text} for {self.question.question_text}"

class ClientQuizResponse(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    selected_answer = models.ForeignKey(QuizAnswer, on_delete=models.CASCADE)
    response_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Response by {self.client.user.username} for {self.question}"



class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('create_contract', 'Create Contract'),
        ('update_profile', 'Update Profile'),
        ('send_payment', 'Send Payment'),
        # Add more as needed
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    target_object = models.CharField(max_length=100, null=True, blank=True)
    details = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"
    

class AdminDashboard:
    @staticmethod
    def get_dashboard_summary():
        contractors_count = Contractor.objects.count()
        clients_count = Client.objects.count()
        outstanding_invoices = Invoice.objects.filter(status='Unpaid').count()
        paid_invoices = Invoice.objects.filter(status='Paid').count()

        return {
            "total_contractors": contractors_count,
            "total_clients": clients_count,
            "outstanding_invoices": outstanding_invoices,
            "paid_invoices": paid_invoices,
        }
    
class CustomOutstandingToken(OutstandingToken):
    my_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    class Meta:
        abstract = True



class Conversation(models.Model):
    participants = models.ManyToManyField(User)
    created_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, related_name="messages", on_delete=models.CASCADE
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)



class ContractConsent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    contract_id = models.IntegerField()  # Assuming each contract has a unique ID
    consent_given = models.BooleanField(default=False)
    signed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consent by {self.user.username} for Contract {self.contract_id}"