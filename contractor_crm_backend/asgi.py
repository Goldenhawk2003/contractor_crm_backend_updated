"""
ASGI config for contractor_crm_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import contractors.routing  # Make sure this imports your app's routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'contractor_crm_backend.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            contractors.routing.websocket_urlpatterns  # Ensure this is properly referenced
        )
    ),
})