from celery import shared_task
from django.core.mail import send_mail
from .models import Invoice
from django.utils.timezone import now

@shared_task
def send_invoice_reminders():
    overdue_invoices = Invoice.objects.filter(due_date__lt=now(), status='Unpaid')
    
    for invoice in overdue_invoices:
        client_email = invoice.contract.client.email  # Assuming the client has an email field
        send_mail(
            'Invoice Overdue Reminder',
            f'Your invoice #{invoice.id} is overdue. Please make payment.',
            'from@example.com',
            [client_email],
            fail_silently=False,
        )
        





