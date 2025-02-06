from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework_simplejwt.tokens import OutstandingToken
from django.core.exceptions import ValidationError
import os
from django.utils.text import slugify
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
    location = models.CharField(max_length=255, blank=True, null=True)
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
      # Add hourly rate

# Contractor model linked to User
class Contractor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='contractor_profile')
    job_type = models.CharField(max_length=100, null=True, blank=True)
    experience_years = models.IntegerField(default=0, null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    total_ratings_count = models.IntegerField(default=0, null=True, blank=True)
    total_ratings_sum = models.IntegerField(default=0, null=True, blank=True)
    profile_description = models.TextField(blank=True, null=True)
    picture = models.ImageField(upload_to='contractor_pictures/', blank=True, null=True)  # Optional picture
    location = models.CharField(max_length=255, blank=True, null=True)  # Optional location
    hourly_rate = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)  # Add hourly rate # Add hourly rate
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)

    
    def __str__(self):
        return self.user.username


# Contract model between client and contractor
class Contract(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()  # Stores the full terms of the contract
    sent_at = models.DateTimeField(auto_now_add=True)
    is_signed = models.BooleanField(default=False)
    recipient = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    ) 
    sender = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="sent_contracts_from_contracts",  # Unique related_name for sender
        null=True, 
        blank=True
    )
    def __str__(self):
        return self.title
    
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
    due_date = models.DateTimeField()  
    status = models.CharField(max_length=50, default='Unpaid') 

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
     
        total_paid = sum(payment.payment_amount for payment in self.invoice.payments.all())
        if total_paid >= self.invoice.amount_due:
            self.invoice.status = 'Paid'
            Contract.status = 'completed'
        else:
            self.invoice.status = 'Partially Paid'
        self.invoice.save()

class QuizQuestion(models.Model):
    question_text = models.CharField(max_length=255)
    job_type_association = models.CharField(max_length=100)  

    def __str__(self):
        return self.question_text

class QuizAnswer(models.Model):
    question = models.ForeignKey(QuizQuestion, related_name='answers', on_delete=models.CASCADE)
    answer_text = models.CharField(max_length=255)
    job_type = models.CharField(max_length=100)  

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
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="consents") 
    consent_given = models.BooleanField(default=False)
    signed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consent by {self.user.username} for Contract {self.contract_id}"
    

class ServiceRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    request = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)



class SentContract(models.Model):
    contractor = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="sent_contracts",  
    )
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_contracts')
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    is_signed = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.contract.title} sent to {self.client.username} by {self.contractor.username}"
    


class ContractorApplication(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    job_type = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    logo = models.ImageField(upload_to="applications/logos/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=[("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")], default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    email = models.EmailField(max_length=255, default="test@gmail.com")

def validate_video_or_image(value):
    valid_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.jpg', '.jpeg', '.png', '.gif']
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in valid_extensions:
        raise ValidationError(f"Unsupported file extension: {ext}. Allowed extensions: {', '.join(valid_extensions)}")


class Tutorials(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    video = models.FileField(upload_to="tutorials/videos/", validators=[validate_video_or_image])
    thumbnail = models.ImageField(upload_to="tutorials/thumbnails/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    views = models.PositiveIntegerField(default=0)

    likes = models.ManyToManyField(User, related_name="liked_tutorials", blank=True)

    def total_likes(self):
        return self.likes.count()

    def __str__(self):
        return self.title
    


class Blog(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blogs")
    title = models.CharField(max_length=255)
    content = models.TextField()
    image = models.ImageField(upload_to="blogs/images/", blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    replies = models.ManyToManyField(User, through="BlogReply", related_name="replies", blank=True)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            unique_slug = base_slug
            num = 1
            while Blog.objects.filter(slug=unique_slug).exists():
                unique_slug = f"{base_slug}-{num}"  # Append numbers to duplicate slugs
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class BlogReply(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply by {self.user.username} on {self.blog.title}"

