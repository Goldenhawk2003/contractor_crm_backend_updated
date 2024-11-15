from django.shortcuts import render
from rest_framework import viewsets, permissions
from .models import Contractor, Contract, Client, Invoice, Payment, Message
from .serializer import ContractorSerializer, ContractSerializer, ClientSerializer, InvoiceSerializer, PaymentSerializer, MessageSerializer
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
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt




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

# ViewSet for Contractors
class ContractorViewSet(viewsets.ModelViewSet):
    queryset = Contractor.objects.all().order_by('id')
    serializer_class = ContractorSerializer
    permission_classes = [IsAuthenticated, IsContractorOrReadOnly, IsAdminUser]
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
    
class MessageViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Customize the queryset to show only messages involving the authenticated user
    def get_queryset(self):
        user = self.request.user
        return Message.objects.filter(sender=user) | Message.objects.filter(receiver=user)

    # When creating a message, set the sender to the authenticated user
    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

def room(request, room_name):
    
    return render(request, 'chat/room.html', {
        'room_name': room_name
    })



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
def admin_dashboard(request):
    total_contractors = Contractor.objects.count()
    total_clients = Client.objects.count()
    outstanding_invoices = Invoice.objects.filter(status='outstanding').count()
    paid_invoices = Invoice.objects.filter(status='paid').count()
    
    # Fetch form responses for the logged-in user
    form_responses = FormResponse.objects.filter(user=request.user)
    
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
    email = request.data.get('email')
    password = request.data.get('password')
    role = request.data.get('role')  # either 'client' or 'professional'

    if role not in ['client', 'professional']:
        return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(
        username=request.data.get('username'),
        email=email,
        password=password,
        user_type=role  # Custom field in your User model
    )
    user.save()


    if user.user_type == 'professional':
            Contractor.objects.create(user=user)  # Assuming you have a foreign key to User in Contractor
    if user.user_type == 'client':
            Client.objects.create(user=user) 
    return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)




@api_view(['POST'])
@permission_classes([AllowAny])
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
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
    })


def csrf_token_view(request):
    # Generates a new CSRF token for the client
    token = get_token(request)
    return JsonResponse({'csrfToken': token})