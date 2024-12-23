from django.contrib.auth import logout
from django.http import JsonResponse

def user_logout(request):
    if request.method == 'POST':
        logout(request)
        return JsonResponse({"message": "Successfully logged out"})
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)