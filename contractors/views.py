from django.shortcuts import render
from rest_framework import viewsets, permissions
from .models import Contractor, Contract, Client, Invoice, Payment, Message, Conversation, ContractConsent, ServiceRequest, ContractorApplication, ClientQuizResponse, Tutorials, Blog, BlogReply
from .serializer import ContractorSerializer, ContractSerializer, ClientSerializer, InvoiceSerializer, PaymentSerializer, MessageSerializer, ConversationSerializer, ServiceRequestSerializer, SendContractSerializer, TutorialsSerializer, BlogSerializer, BlogReplySerializer
from .models import FormResponse, Quiz
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework import status
from .permissions import IsContractor, IsPaymentOwner, IsContractorOrClientForContract, IsAdminUser, IsClientOrReadOnly, IsContractorOrReadOnly
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend 
from rest_framework.filters import SearchFilter
from .services import QuizMatchService
from rest_framework.views import APIView
from .models import ActivityLog, AdminDashboard
from django.template import TemplateDoesNotExist
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login, logout
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import logging
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse, Http404
import json
from django.contrib.auth.decorators import user_passes_test
from rest_framework.generics import RetrieveAPIView
from django.utils.decorators import method_decorator
import base64
import requests
from urllib.parse import urlencode
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, Tabs, SignHere, RecipientViewRequest, Recipients
from django.core.mail import send_mail
from contractor_crm_backend import settings
import stripe
from django.http import HttpResponse
import logging
from django.db.models import Q
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils.timezone import now  # Import now from django.utils.timezone
from .models import SentContract, Contract, User
from django.utils import timezone
from rest_framework.parsers import JSONParser
from django.core.exceptions import ObjectDoesNotExist
from collections import defaultdict
from django.db.models import Max
from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser

# this is a scraped view that is supposed to use your quiz answers to suggest a contractor
# Ultimaltely it was decided that for now a manual selection of a contractor would be better
def suggest_contractor_based_on_answer(answer):
    contractor = Contractor.objects.filter(job_type__icontains=answer).first()
    return contractor

# View to record the client's quiz response
def submit_quiz_response(request):
    if request.method == 'POST':
        answer = request.POST.get('answer')
        client = request.user  # Assuming the client is logged in otherwise it wont send through
        quiz = Quiz.objects.get(id=request.POST.get('quiz_id'))

        # Get contractor suggestion based on the answer
        suggested_contractor = suggest_contractor_based_on_answer(answer)

        # Create a form response
        form_response = FormResponse.objects.create(
            client=client,
            quiz=quiz,
            answer=answer,
            contractor_suggestion=suggested_contractor
        )

        # Render a response or redirect
        return render(request, 'quiz_result.html', {'form_response': form_response})

    return render(request, 'quiz.html') # The template was scrapped in order to keep everything on the frontend flowing through react

# View to display the quiz questions
def get_quiz_questions(request):
    # Fetch all quiz questions
    if request.method == 'GET':
        questions = Quiz.objects.all()
        question_list = []
        # Prepare the questions for JSON response
        for question in questions:
            question_data = {
                "id": question.id,
                "text": question.question,
                "type": question.question_type,
                "description": question.description,
            }
            if question.question_type == "multiple_choice":
                question_data["choices"] = question.choices

            question_list.append(question_data)

        return JsonResponse({"questions": question_list}, safe=False)

# View to submit a quiz response
@csrf_exempt
@login_required
def submit_quiz_response(request):
    if request.method == 'POST':
        # Parse request data
        data = json.loads(request.body)
        quiz_id = data.get('quiz_id')
        answer = data.get('answer')

        # Validate input
        quiz = get_object_or_404(Quiz, id=quiz_id)

        # Save response
        FormResponse.objects.create(
            client=request.user,  # Ensure the user is authenticated
            quiz=quiz,
            answer=answer,
        )

        return JsonResponse({"message": "Response submitted successfully!"}, status=201)

    return JsonResponse({"error": "Invalid request method"}, status=400)

# View to display the form responses dashboard, in this project form and quiz are used interchangebly
def form_responses_dashboard(request):
    if request.method == "GET":
        # Query all form responses
        responses = FormResponse.objects.select_related('client', 'quiz', 'contractor_suggestion').all()

        # Group responses by username to make it easier to display
        grouped_responses = defaultdict(list)
        for response in responses:
            grouped_responses[response.client.username].append({
                'quiz_question': response.quiz.question,
                'answer': response.answer,
                'selected_choice': response.selected_choice,
                'contractor_suggestion': response.contractor_suggestion.name if response.contractor_suggestion else None,
                'created_at': response.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        # Prepare data for JSON response
        response_data = [{'client': client, 'responses': resp_list} for client, resp_list in grouped_responses.items()]

        # Return as JSON
        return JsonResponse({'responses': response_data}, status=200)

    # Handle invalid methods
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# View to add a new question to the quiz (form) from the admin panel on the site
@csrf_exempt
def add_question(request):
    # Only allow POST requests
    if request.method == "POST":
        # Parse the request data
        try:
            data = json.loads(request.body)
            question_text = data.get("question")
            question_type = data.get("question_type", "text")
            description = data.get("description", "")
            choices = data.get("choices", None)

            if not question_text:
                return JsonResponse({"error": "Question text is required."}, status=400)

            # Validate choices for multiple-choice questions
            if question_type == "multiple_choice" and not choices:
                return JsonResponse({"error": "Choices are required for multiple-choice questions."}, status=400)

            question = Quiz.objects.create(
                question=question_text,
                description=description,
                question_type=question_type,
                choices=choices if question_type == "multiple_choice" else None,
            )
            return JsonResponse({"message": "Question added successfully.", "id": question.id}, status=201)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed."}, status=405) # If the request method is not POST

# View to delete a question from the quiz (form) from the admin panel on the site
@csrf_exempt
def delete_question(request, question_id):
    if request.method == "DELETE":
        try:
            question = Quiz.objects.get(id=question_id)
            question.delete()
            return JsonResponse({"message": "Question deleted successfully."}, status=200)
        except Quiz.DoesNotExist:
            return JsonResponse({"error": "Question not found."}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed."}, status=405) # If the request method is not DELETE

def list_questions(request):
    if request.method == "GET":
        questions = Quiz.objects.all()
        response_data = [
            {
                "id": question.id,
                "question": question.question,
                "description": question.description,
                "question_type": question.question_type,
                "choices": question.choices,
            }
            for question in questions
        ]
        return JsonResponse({"questions": response_data}, status=200)

    return JsonResponse({"error": "Method not allowed."}, status=405)

# ViewSet for Contractors
@permission_classes([AllowAny])
class ContractorViewSet(viewsets.ModelViewSet):
    queryset = Contractor.objects.all().order_by('job_type')
    serializer_class = ContractorSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter]  # Enable filtering
    filterset_fields = ['job_type', 'location'] 
    search_field = ['name', 'job_type']

    def perform_update(self, serializer):
        """
        Ensure that the contractor is only updating their own profile.
        """
        contractor = self.request.user  # Assuming the contractor is linked to the user
        serializer.save(user=contractor)
    def get_queryset(self):
        # Restrict to only the logged-in contractor's profile
        if self.request.user.groups.filter(name='Contractor').exists():
            return Contractor.objects.filter(user=self.request.user)
        return super().get_queryset()

# ViewSet for Contracts
class ContractListView(APIView):
    def get(self, request):
        contracts = Contract.objects.all()
        data = [
            {
                "id": contract.id,
                "title": contract.title,
                "content": contract.content,
            }
            for contract in contracts
        ]
        return Response(data, status=status.HTTP_200_OK)

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsClientOrReadOnly, IsAdminUser]

    def get_queryset(self):
        if self.request.user.groups.filter(name='Client').exists():
            return Invoice.objects.filter(client=self.request.user.client)
        elif self.request.user.groups.filter(name='Contractor').exists():
            return Invoice.objects.filter(contract__contractor=self.request.user.contractor)
        return super().get_queryset()

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsPaymentOwner, IsAdminUser] # Only authenticated users can access this viewset
    
    def perform_create(self, serializer):
        payment = serializer.save()

        # Update the related invoice status
        invoice = payment.invoice
        total_payments = sum([p.amount_paid for p in invoice.payment_set.all()])

        if total_payments >= invoice.amount_due:
            invoice.status = 'Paid'
        elif invoice.due_date < payment.payment_date:
            invoice.status = 'Overdue'
        else:
            invoice.status = 'Unpaid'

        invoice.save()

@api_view(['POST'])
def register(request):
    username = request.data.get('username')
    password = request.data.get('password')
    
    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already taken"}, status=status.HTTP_400_BAD_REQUEST)
    
    user = User.objects.create_user(username=username, password=password)
    return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)

class QuizSubmitView(APIView):
    def post(self, request, *args, **kwargs):
        client = request.user.client
        # Assuming quiz answers have been saved in ClientQuizResponse
        service = QuizMatchService()
        matched_contractors = service.match_client_to_contractor(client)
        
        # Return the matched contractors to the client
        serializer = ContractorSerializer(matched_contractors, many=True)
        return Response(serializer.data)
    



def test_view(request):
    return render(request, 'test.html', {})

def log_activity(user, action, target_object=None, details=None):
    ActivityLog.objects.create(
        user=user,
        action=action,
        target_object=target_object,
        details=details
    )

@api_view(['GET'])
@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    total_contractors = Contractor.objects.count()
    total_clients = Client.objects.count()
    outstanding_invoices = Invoice.objects.filter(status='outstanding').count()
    paid_invoices = Invoice.objects.filter(status='paid').count()

    # User growth analytics
    user_growth = (
        User.objects.filter(date_joined__isnull=False)
        .annotate(date=TruncDate("date_joined"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    # Fetch pending contractor applications
    pending_applications = ContractorApplication.objects.filter(status='Pending')

    # Prepare application data for the response
    pending_applications_data = []
    for app in pending_applications:
        try:
            user = User.objects.get(id=app.user_id)  # Fetch user details
            pending_applications_data.append({
                "id": app.id,
                "username": user.username,  # Access username via User model
                "job_type": app.job_type,
                "location": app.location,
                "hourly_rate": str(app.hourly_rate),
                "logo": app.logo.url if app.logo else None,
                "status": app.status,
                "email": user.email,
            })
        except User.DoesNotExist:
            # Log or handle missing user case
            pass


    recent_service_requests = ServiceRequest.objects.order_by('-created_at')[:5]
    recent_requests_data = [
        {
            "id": req.id,
            "user": req.user.username,  # Assuming user is a ForeignKey to your User model
            "request": req.request,
            "created_at": req.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for req in recent_service_requests
    ]

    # Return the data
    return Response({
        'total_contractors': total_contractors,
        'total_clients': total_clients,
        'outstanding_invoices': outstanding_invoices,
        'paid_invoices': paid_invoices,
         "pending_applications": pending_applications_data,
        'recent_service_requests': recent_requests_data,  # Include recent requests
    })
    



User = get_user_model()

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    logger = logging.getLogger(__name__)
    logger.info(f"Received data: {request.data}")

    required_fields = ['username', 'firstname', 'lastname', 'email', 'password', 'location', 'role']
    missing_fields = [field for field in required_fields if not request.data.get(field)]

    if missing_fields:
        return Response(
            {"error": f"Missing fields: {', '.join(missing_fields)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    username = request.data.get('username')
    firstname = request.data.get('firstname')
    lastname = request.data.get('lastname')
    email = request.data.get('email')
    password = request.data.get('password')
    location = request.data.get("location")
    role = request.data.get('role')
    job_type = request.data.get('job_type', None)
    hourly_rate = request.data.get('hourly_rate', None)
    logo = request.FILES.get("logo")

    if role not in ['client', 'professional']:
        return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    if role == 'professional' and not job_type:
        return Response({"error": "Job type is required for professionals"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if role == 'client':
            # Register client immediately
            user = User.objects.create_user(
                username=username,
                first_name=firstname,
                last_name=lastname,
                email=email,
                password=password,
                location=location,
                user_type=role,
                is_active=True  # Clients are activated immediately
            )
            Client.objects.create(user=user)
            logger.info(f"Client {username} registered successfully")
            return Response(
                {"message": "Client registered successfully", "id": user.id},
                status=status.HTTP_201_CREATED
            )

        elif role == 'professional':
            # Register contractor as inactive and create an application
            user = User.objects.create_user(
                username=username,
                first_name=firstname,
                last_name=lastname,
                email=email,
                password=password,
                location=location,
                user_type=role,
                is_active=False  # Contractors require admin approval
            )
            ContractorApplication.objects.create(
                user=user,
                job_type=job_type,
                location=location,
                hourly_rate=hourly_rate,
                logo=logo
            )
            logger.info(f"Contractor application for {username} submitted successfully")
            return Response(
                {"message": "Contractor application submitted successfully. Pending admin approval.", "id": user.id},
                status=status.HTTP_201_CREATED
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
def login_view(request):
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({"success": "Logged in successfully."}, status=200)
        return JsonResponse({"error": "Invalid credentials."}, status=400)
    return JsonResponse({"error": "Invalid request method."}, status=405)


@login_required  # Ensures only authenticated users can access this view
def get_user_info(request):
    permission_classes = [IsAuthenticated]
    user = request.user

    # Check if the user is a contractor and fetch additional info if they are
    contractor_info = None
    if user.user_type == "professional":  # Assuming "professional" indicates contractors
        try:
            contractor = Contractor.objects.get(user=user)
            contractor_info = {
                'logo': contractor.logo.url if contractor.logo else None,
                'location': contractor.location if contractor.location else None,
            }
        except Contractor.DoesNotExist:
            contractor_info = {'logo': None}

    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'type': user.user_type,
  
        **(contractor_info or {}),  # Add contractor-specific info if available
    })

def user_info(request):
    user = request.user
    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,  # Include this field
    })

def csrf_token_view(request):
    # Generates a new CSRF token for the client
    token = get_token(request)
    return JsonResponse({'csrfToken': token})

@permission_classes([AllowAny])
class ContractorByUserView(RetrieveAPIView):
    queryset = Contractor.objects.all()
    serializer_class = ContractorSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        user_id = self.kwargs['user_id']
        return Contractor.objects.get(user_id=user_id)
    


class ConversationListView(APIView):
    def get(self, request):
        user = request.user
        conversations = Conversation.objects.filter(participants=request.user)
        serializer = ConversationSerializer(conversations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def get_queryset(self):
        # Annotate conversations with the latest message timestamp
        return Conversation.objects.annotate(
            latest_message_time=Max('messages__timestamp')
        ).order_by('-latest_message_time') 

class MessageListView(APIView):
    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id, participants=request.user)
            serializer = MessageSerializer(conversation.messages.all(), many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

class CreateMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sender = request.user
        recipient_id = request.data.get("recipient_id")
        content = request.data.get("content")

        if not recipient_id or not content:
            return Response({"error": "Recipient and content are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return Response({"error": "Recipient not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check if a conversation exists
        conversation = Conversation.objects.filter(participants=sender).filter(participants=recipient).first()

        # If no conversation exists, create a new one
        if not conversation:
            conversation = Conversation.objects.create()
            conversation.participants.set([sender, recipient])  # Assign participants

        # Create the message
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content,
        )

        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    


@method_decorator(csrf_exempt, name='dispatch')  # Disable CSRF for this view
class ContactView(APIView):
    permission_classes = [AllowAny]  # Ensure the endpoint is publicly accessible

    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')
        message = request.data.get('message')
        role = request.data.get('role')

        # Validate required fields
        if not (first_name and last_name and email and message and role):
            return Response(
                {"error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Compose the email
        subject = f"New Contact Us Submission from {first_name} {last_name}"
        body = f"""
        Name: {first_name} {last_name}
        Email: {email}
        Role: {role}

        Message:
        {message}
        """
        try:
            send_mail(
                subject,
                body,
                'your-email@example.com',  # Replace with your "from" email address
                ['info@elitecraftcontractors.com'],  # Replace with the recipient email
                fail_silently=False,
            )
            return Response(
                {"success": "Your message has been sent successfully!"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            # Log the exception and return a user-friendly error
            print(f"Email sending failed: {str(e)}")
            return Response(
                {"error": "Failed to send email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        



def send_contract(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            print("Payload received:", data)

            user_id = data.get("user_id")
            contract_title = data.get("title")  # Fetch the title from the request
            contract_content = data.get("contractContent")

            # Validate inputs
            if not user_id or not contract_title or not contract_content:
                print("Validation failed: Missing required fields.")
                return JsonResponse({"error": "Missing required fields."}, status=400)

            # Check if user exists
            try:
                recipient = User.objects.get(id=user_id)
                print("Recipient found:", recipient)
            except User.DoesNotExist:
                print("Validation failed: User not found.")
                return JsonResponse({"error": "User not found."}, status=404)

            # Create the contract
            contract = Contract.objects.create(
                title=contract_title,
                content=contract_content,
                recipient=recipient,
                sender=request.user
            )
            print("Contract created:", contract)

            return JsonResponse({"message": "Contract sent successfully."}, status=201)

        except Exception as e:
            print("Error occurred:", str(e))
            return JsonResponse({"error": str(e)}, status=500)

    print("Invalid request method.")
    return JsonResponse({"error": "Invalid request method."}, status=405)




def get_received_contracts(request):
    contracts = Contract.objects.filter(recipient=request.user)
    data = [
        {
            "id": contract.id,
            "title": contract.title,
            "content": contract.content,
            "is_signed": contract.is_signed,
            "sent_at": contract.sent_at,
        }
        for contract in contracts
    ]
    return JsonResponse({"contracts": data}, status=200)

@login_required  # Ensure the user is authenticated
def sign_contract(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            contract_id = data.get("contract_id")

            if not contract_id:
                return JsonResponse({"error": "Contract ID is required."}, status=400)

            contract = Contract.objects.get(id=contract_id, recipient=request.user)

            if contract.is_signed:
                return JsonResponse({"error": "Contract is already signed."}, status=400)

            contract.is_signed = True
            contract.save()

            return JsonResponse({"message": "Contract signed successfully."}, status=200)

        except Contract.DoesNotExist:
            return JsonResponse({"error": "Contract not found."}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=405)

@login_required
def get_user_consents(request):
    user = request.user
    consents = ContractConsent.objects.filter(user=user, consent_given=True).values(
        "contract_id", "signed_at"
    )
    return JsonResponse({"consents": list(consents)}, status=200)

logger = logging.getLogger(__name__)

def get_sent_contracts(request):
    if request.method == "GET":
        contractor = request.user
        print(f"Logged-in user: {contractor}")  # Debug log

        sent_contracts = Contract.objects.filter(sender=contractor)  # Filter contracts sent by this user
        print(f"Sent contracts for {contractor}: {sent_contracts}")  # Debug log

        data = [
            {
                "id": contract.id,
                "title": contract.title,
                "recipient": contract.recipient.username if contract.recipient else "Unknown",
                "is_signed": contract.is_signed,
                "sent_at": contract.sent_at,
            }
            for contract in sent_contracts
        ]

        return JsonResponse({"contracts": data}, status=200)

    return JsonResponse({"error": "Invalid request method."}, status=405)


stripe.api_key = settings.STRIPE_SECRET_KEY
@csrf_exempt
def create_payment_intent(request):
    try:
        # Amount in cents (e.g., $10.00)
        amount = 1000  # Customize based on your service price
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            payment_method_types=["card"],  # Other types: 'sepa_debit', 'ideal', etc.
        )
        return JsonResponse({"clientSecret": intent["client_secret"]})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    

logger = logging.getLogger(__name__)

@csrf_exempt
def stripe_webhook(request):
    logger.info("Webhook hit!")
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = 'whsec_REdVGgxFAG3yWgIMWdWb4SgNWogO7XNe'

    logger.info(f"Payload: {payload}")
    logger.info(f"Signature Header: {sig_header}")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return HttpResponse(status=400)

    logger.info(f"Received event: {event['type']}")

    return HttpResponse(status=200)


logger = logging.getLogger(__name__)
@csrf_exempt
def create_invoice(request):
    try:
        # Create a customer (if not already created)
        customers = stripe.Customer.list(email="ammarogeil@gmail.com").data
        if customers:
            customer = customers[0]
        else:
            customer = stripe.Customer.create(
                email="ammarogeil@gmail.com",
                name="John Doe"
            )

        # Create a product
        product = stripe.Product.create(name="Service/Product Name")

        # Create a price for the product
        price = stripe.Price.create(
            product=product.id,
            unit_amount=1000,  # Amount in cents (e.g., $10.00)
            currency="usd"
        )

        # Create an invoice item
        stripe.InvoiceItem.create(
            customer=customer.id,
            price=price.id
        )

        # Create the invoice with collection_method set to 'send_invoice'
        invoice = stripe.Invoice.create(
            customer=customer.id,
            collection_method="send_invoice",  # Change to manual invoicing
            days_until_due=30  # Optional: Set payment terms
        )

        # Send the invoice
        stripe.Invoice.send_invoice(invoice.id)

        return JsonResponse({"message": "Invoice created and sent successfully!"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    


def search_users(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse([], safe=False)

    users = User.objects.filter(Q(username__icontains=query))
    results = [{"id": user.id, "username": user.username} for user in users]
    return JsonResponse(results, safe=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reply_to_conversation(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    content = request.data.get("content", "")

    if not content.strip():
        return Response({"error": "Message content cannot be empty."}, status=400)

    # Create the reply message
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content,
    )

    return Response({"message": "Reply sent successfully.", "id": message.id}, status=201)




logger = logging.getLogger(__name__)

class ServiceRequestView(APIView):
    def post(self, request):
        serializer = ServiceRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        service_request_text = serializer.validated_data['searchText']
        
        try:
            # Create and save the ServiceRequest object
            service_request = ServiceRequest.objects.create(
                user=request.user,
                request=service_request_text,
                created_at=now()
            )

            logger.info(f"Service request received from user {request.user.id}: {service_request_text}")

            return Response({
                "message": "Service request submitted successfully!",
                "details": {
                    "id": service_request.id,
                    "user": request.user.username,
                    "request": service_request.request,
                    "created_at": service_request.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            # Log the exception
            logger.error(f"Error processing service request: {str(e)}")
            
            return Response(
                {"error": "Failed to process service request. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@api_view(['POST'])
def rate_contractor(request, id):
    contractor = get_object_or_404(Contractor, id=id)
    rating = request.data.get('rating')

    if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
        return Response({"error": "Invalid rating value."}, status=status.HTTP_400_BAD_REQUEST)

    # Update average rating
    if contractor.total_ratings_count is None:
        contractor.total_ratings_count = 0
        contractor.total_ratings_sum = 0
    contractor.total_ratings_sum += rating
    contractor.total_ratings_count += 1
    contractor.rating = contractor.total_ratings_sum / contractor.total_ratings_count
    contractor.save()

    return Response({
        "message": "Rating submitted successfully.",
        "rating": contractor.rating,
        "total_ratings_count": contractor.total_ratings_count
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
def handle_application(request, application_id):
    action = request.data.get('action')  # "accept" or "reject"
    application = get_object_or_404(ContractorApplication, id=application_id)

    if action == "accept":
        try:
            application.user.is_active = True
            application.user.save()
            # Create a Contractor from the application
            Contractor.objects.create(
                user=application.user,
                job_type=application.job_type,
                location=application.location,
                hourly_rate=application.hourly_rate,
                logo=application.logo,
      
        
            )
            # Delete the application after successful acceptance
            application.delete()
            return Response({"message": "Contractor added successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    elif action == "reject":
        # Delete the application
        application.delete()
        return Response({"message": "Application rejected and deleted."}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_contractor(request, id):
    try:
        # Get the contractor application by ID
        application = ContractorApplication.objects.get(id=id)
        application.user.is_active = True
        application.user.save()
        # Create a new contractor and delete the application
        Contractor.objects.create(
            user=application.user,
            job_type=application.job_type,
            location=application.location,
            hourly_rate=application.hourly_rate,
            logo=application.logo,

        )
        application.delete()
        return Response({"message": "Contractor approved successfully."}, status=status.HTTP_200_OK)

    except ContractorApplication.DoesNotExist:
        return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_contractor(request, id):
    try:
        application = ContractorApplication.objects.get(id=id)
        application.delete()
        return Response({"message": "Contractor application rejected successfully."}, status=status.HTTP_200_OK)

    except ContractorApplication.DoesNotExist:
        return Response({"error": "Contractor application not found."}, status=status.HTTP_404_NOT_FOUND)
    

def get_user_by_username(request, username):
    try:
        user = User.objects.get(username=username)
        return JsonResponse({
            "id": user.id,
            "username": user.username,
            "email": user.email,  # Add other fields as needed
        })
    except User.DoesNotExist:
        raise Http404("User not found")
    


def logout_view(request):
    if request.method == "POST":
        logout(request)  # Clears the session
        return JsonResponse({"message": "Logged out successfully"}, status=200)
    return JsonResponse({"error": "Invalid request method"}, status=405)


class TutorialListCreateView(generics.ListCreateAPIView):
    queryset = Tutorials.objects.all().order_by("-created_at")
    serializer_class = TutorialsSerializer
    permission_classes = [AllowAny] 
    parser_classes = [MultiPartParser, FormParser]

# ✅ Retrieve, Update, or Delete a specific tutorial
class TutorialDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Tutorials.objects.all()
    serializer_class = TutorialsSerializer
    permission_classes = [AllowAny] 
    




@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated]) 
def like_tutorial(request, pk):
    """ Increases the like count for a tutorial """
    """Handle likes and return current like count"""
    try:
        tutorial = Tutorials.objects.get(pk=pk)

        # Handle GET request (return like count)
        if request.method == "GET":
            return Response({"likes": tutorial.total_likes()})

        # Handle POST request (toggle like)
        user = request.user if request.user.is_authenticated else None
        if user:
            if user in tutorial.likes.all():
                tutorial.likes.remove(user)  # Unlike
                message = "Like removed"
            else:
                tutorial.likes.add(user)  # Like
                message = "Like added"
        else:
            message = "Login required to like."

        return Response({"message": message, "likes": tutorial.total_likes()})

    except Tutorials.DoesNotExist:
        return Response({"error": "Tutorial not found"}, status=404)
    
@api_view(['POST'])
def view_tutorial(request, pk):
    """ Increases the view count when a tutorial is opened """
    try:
        tutorial = Tutorials.objects.get(pk=pk)
        tutorial.views += 1  # Increment views
        tutorial.save()
        return Response({"message": "View recorded", "views": tutorial.views})
    except Tutorials.DoesNotExist:
        return Response({"error": "Tutorial not found"}, status=404)
    
class BlogDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Blog.objects.all()
    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
        
    def get_queryset(self):
        
         return Blog.objects.filter(author=self.request.user)
    
class BlogListCreateView(generics.ListCreateAPIView):  # Supports GET & POST
    queryset = Blog.objects.all().order_by("-created_at")
    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
class BlogReplyCreateView(generics.CreateAPIView):
    queryset = BlogReply.objects.all()
    serializer_class = BlogReplySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        blog_id = self.kwargs.get("pk")  # Get blog ID from URL
        blog = get_object_or_404(Blog, pk=blog_id)
        serializer.save(blog=blog, user=self.request.user) 