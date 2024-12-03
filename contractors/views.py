from django.shortcuts import render
from rest_framework import viewsets, permissions
from .models import Contractor, Contract, Client, Invoice, Payment, Message, Conversation
from .serializer import ContractorSerializer, ContractSerializer, ClientSerializer, InvoiceSerializer, PaymentSerializer, MessageSerializer, ConversationSerializer
from .models import FormResponse, Quiz
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
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
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import logging
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
import json
from django.contrib.auth.decorators import user_passes_test
from rest_framework.generics import RetrieveAPIView
from django.utils.decorators import method_decorator
import base64
import requests
from urllib.parse import urlencode
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, Document, Signer, Tabs, SignHere
from django.core.mail import send_mail




# Function to suggest a contractor based on the client's answer
def suggest_contractor_based_on_answer(answer):
    # Match contractors based on the client's answer
    contractor = Contractor.objects.filter(job_type__icontains=answer).first()
    return contractor

# View to handle form submission and contractor matching
def submit_quiz_response(request):
    if request.method == 'POST':
        answer = request.POST.get('answer')
        client = request.user  # Assuming the client is logged in
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

    return render(request, 'quiz.html') # Assuming you have a quiz form template


def get_quiz_questions(request):
    if request.method == 'GET':
        questions = Quiz.objects.all()
        question_list = []

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

# ViewSet for Contractors
@permission_classes([AllowAny])
class ContractorViewSet(viewsets.ModelViewSet):
    queryset = Contractor.objects.all().order_by('job_type')
    serializer_class = ContractorSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter]  # Enable filtering
    filterset_fields = ['job_type'] 
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
class ContractViewSet(viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated, IsContractorOrClientForContract]

    def get_queryset(self):
        if self.request.user.groups.filter(name='Contractor').exists():
            return Contract.objects.filter(contractor=self.request.user.contractor)
        elif self.request.user.groups.filter(name='Client').exists():
            return Contract.objects.filter(client=self.request.user.client)
        return super().get_queryset()
    
    def perform_update(self, serializer):
        # Save the contract changes first
        contract = serializer.save()

        # Update the related invoice (if it exists)
        invoice = Invoice.objects.filter(contract=contract).first()
        if invoice:
            invoice.amount_due = contract.total_amount
            invoice.due_date = contract.due_date
            invoice.save()
    def perform_create(self, serializer):
        # Save the contract first
        contract = serializer.save()
        log_activity(user=self.request.user, action='create_contract', target_object=f"Contract ID {contract.id}", details="Contract creation details")

        # Automatically create an invoice linked to this contract
        Invoice.objects.create(
            contract=contract,
            client=contract.client,
            contractor=contract.contractor,
            amount_due=contract.total_amount,
            due_date=contract.due_date
        )

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
    
    # Fetch form responses for the logged-in user
    form_responses = FormResponse.objects.filter(client=request.user)
    
    # Return data to frontend
    return Response({
        'total_contractors': total_contractors,
        'total_clients': total_clients,
        'outstanding_invoices': outstanding_invoices,
        'paid_invoices': paid_invoices,
        'form_responses': [{'response': response.response} for response in form_responses]
    })
    



User = get_user_model()

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    
    logger = logging.getLogger(__name__)
    logger.info(f"Received data: {request.data}")

    # Validate required fields
    required_fields = ['username', 'email', 'password', 'role']
    missing_fields = [field for field in required_fields if not request.data.get(field)]
    
    if missing_fields:
        return Response(
            {"error": f"Missing fields: {', '.join(missing_fields)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')
    confirm_password = request.data.get('confirmPassword', None)
    role = request.data.get('role')
    job_type = request.data.get('job_type', None) 
    print(f"Job Type: {job_type}") # Default to None if not provided

    # Validate passwords match
    if confirm_password and password != confirm_password:
        return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate role
    if role not in ['client', 'professional']:
        return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate job_type for professionals
    if role == 'professional' and not job_type:
        return Response(
            {"error": "Job type is required for professionals"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Check for duplicate username or email
        if User.objects.filter(username__iexact=username).exists():
            return Response({"error": "Username already taken"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=email).exists():
            return Response({"error": "Email already in use"}, status=status.HTTP_400_BAD_REQUEST)

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            user_type=role
        )

        # Create role-specific data
        if role == 'professional':
            Contractor.objects.create(user=user, job_type=job_type)
        elif role == 'client':
            Client.objects.create(user=user)

        logger.info(f"User {username} registered successfully")
        return Response(
            {"message": "User registered successfully", "id": user.id, "role": user.user_type},
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return Response(
            {"error": "An unexpected error occurred"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def login_view(request):
    """Handles login"""
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(request, username=username, password=password)

    if user is not None:
        login(request, user)  # Logs the user in by creating a session
        return JsonResponse({"message": "Login successful"})
    else:
        return JsonResponse({"error": "Invalid username or password"}, status=400)

@login_required  # Ensures only authenticated users can access this view
def get_user_info(request):
    # Access the logged-in user
    user = request.user

    # Return some user information in the response
    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'type': user.user_type
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

class MessageListView(APIView):
    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id, participants=request.user)
            serializer = MessageSerializer(conversation.messages.all(), many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

@method_decorator(csrf_exempt, name="dispatch")
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
    
DOCUSIGN_AUTH_URL = "https://account-d.docusign.com/oauth/auth"
TOKEN_URL = "https://account-d.docusign.com/oauth/token"
CLIENT_ID = "a0769e40-cd97-4e92-a79b-8021247aeaf3"
CLIENT_SECRET = "0f55b6ae-77d3-4271-b58c-8a757095da53"
REDIRECT_URI = "http://yourcrm.com/docusign/callback"


def docusign_login(request):
    params = {
        "response_type": "code",
        "scope": "signature",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }
    return redirect(f"{DOCUSIGN_AUTH_URL}?{urlencode(params)}")

def docusign_callback(request):
    code = request.GET.get("code")
    if not code:
        return JsonResponse({"error": "No code provided"}, status=400)

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    auth_header = f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")
    headers = {"Authorization": f"Basic {base64.b64encode(auth_header).decode()}"}
    response = requests.post(TOKEN_URL, data=payload, headers=headers)

    if response.status_code == 200:
        access_token = response.json()["access_token"]
        request.session["docusign_token"] = access_token
        return JsonResponse({"message": "Authenticated successfully"})
    return JsonResponse({"error": response.json()}, status=response.status_code)


def send_contract(request, document_path, signer_email, signer_name):
    access_token = request.session.get("docusign_token")
    if not access_token:
        return JsonResponse({"error": "User not authenticated"}, status=401)

    # Setup API client
    api_client = ApiClient()
    api_client.set_base_path("https://demo.docusign.net/restapi")
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    # Create envelope definition
    with open(document_path, "rb") as file:
        doc_bytes = file.read()

    document = Document(
        document_base64=base64.b64encode(doc_bytes).decode("utf-8"),
        name="Contract",
        file_extension="pdf",
        document_id="1",
    )

    signer = Signer(
        email=signer_email,
        name=signer_name,
        recipient_id="1",
        routing_order="1",
    )

    sign_here = SignHere(anchor_string="/sig/", anchor_units="pixels", anchor_x_offset="20", anchor_y_offset="10")
    signer.tabs = Tabs(sign_here_tabs=[sign_here])

    envelope_definition = EnvelopeDefinition(
        email_subject="Please sign this contract",
        documents=[document],
        recipients={"signers": [signer]},
        status="sent",
    )

    envelopes_api = EnvelopesApi(api_client)
    envelope_summary = envelopes_api.create_envelope(account_id="31467551", envelope_definition=envelope_definition)

    return JsonResponse({"envelopeId": envelope_summary.envelope_id})

def get_envelope_status(request, envelope_id):
    access_token = request.session.get("docusign_token")
    if not access_token:
        return JsonResponse({"error": "User not authenticated"}, status=401)

    api_client = ApiClient()
    api_client.set_base_path("https://demo.docusign.net/restapi")
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    envelopes_api = EnvelopesApi(api_client)
    status = envelopes_api.get_envelope(account_id="31467551", envelope_id=envelope_id)
    return JsonResponse({"status": status.status})

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