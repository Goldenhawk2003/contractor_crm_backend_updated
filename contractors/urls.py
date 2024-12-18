from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ContractorViewSet, ContractListView, InvoiceViewSet, ClientViewSet, PaymentViewSet, register_user,csrf_token_view, get_user_info, get_quiz_questions, submit_quiz_response,ContractorByUserView, ConversationListView, MessageListView, CreateMessageView, ContactView, stripe_webhook, create_payment_intent, create_invoice, ServiceRequestView
from django.contrib import admin
from .views import register
from .views import QuizSubmitView, admin_dashboard
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings
from django.conf.urls.static import static



urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('contractors.urls')),  # Include URLs from the contractors app
    path('register/', register, name='register'),  # Registration endpoint
    path('api/quiz/submit/', QuizSubmitView.as_view(), name='quiz-submit'),
    path('admin/dashboard/', admin_dashboard, name='admin_dashboard'),
    path('test/', views.test_view, name='test'),
    
]
# Set up a router to automatically generate URL patterns for the viewsets
router = DefaultRouter()
router.register(r'contractors', ContractorViewSet)
router.register(r'clients', ClientViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)



urlpatterns = [
    path('', include(router.urls)),  # Include the router-generated URLs
    path('api/register/', register_user, name='register_user'),
    path('api/login/', views.login_view, name='login'),
    path('api/csrf_token/', csrf_token_view),
    path('api/user-info/', get_user_info, name='user-info'),
    path('api/quiz/questions/', get_quiz_questions, name='quiz-questions'),
    path('api/quiz/submit/', submit_quiz_response, name='quiz-submit'),
    path('api/contractors/by-user/<int:user_id>/', ContractorByUserView.as_view(), name='contractor-by-user'),
    path("api/conversations/", ConversationListView.as_view(), name="conversation-list"),
    path("api/conversations/<int:conversation_id>/messages/", MessageListView.as_view(), name="message-list"),
    path("api/messages/", CreateMessageView.as_view(), name="create-message"),
    path("docusign/login/", views.get_docusign_client, name="docusign_login"),
    path('api/send-contract/', views.send_contract, name='send-contract'),
    path("docusign/status/<str:envelope_id>/", views.get_contract_status, name="get_envelope_status"),
    path('contact/', ContactView.as_view(), name='contact'),
    path("api/sign-contract/", views.sign_contract, name="sign-contract"),
    path("api/user-consents/", views.get_user_consents, name="user-consents"),
    path('stripe-webhook/', stripe_webhook, name='stripe_webhook'),
    path('create-payment-intent/', create_payment_intent, name='create_payment_intent'),
    path('create-invoice/', create_invoice, name='create-invoice'),
    path("api/users/search/", views.search_users, name="search_users"),
    path("api/conversations/<int:conversation_id>/reply/", views.reply_to_conversation, name="reply_to_conversation"),
    path('api/request-service/', ServiceRequestView.as_view() , name='service-request'),
    path('contracts/', ContractListView.as_view(), name='contract-list'),
    path('contractors/<int:id>/rate/', views.rate_contractor, name='rate-contractor'),
    path('api/approve-contractor/<int:id>/', views.approve_contractor, name='approve-contractor'),
    path('api/reject-contractor/<int:id>/', views.reject_contractor, name='reject-contractor'),
    path('api/users/username/<str:username>/', views.get_user_by_username, name='get_user_by_username'),
    path("api/received-contracts/", views.get_received_contracts, name="received-contracts"),
    path("api/sent-contracts/", views.get_sent_contracts, name="sent-contracts"),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)