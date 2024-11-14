from rest_framework.permissions import BasePermission


class IsContractor(BasePermission):
    def has_permission(self, request, view):
        # Check if the user belongs to the "Contractor" group
        return request.user.groups.filter(name='Contractor').exists()
    

class IsPaymentOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        # Assuming `obj` is a Payment object, and both contractors and clients can access their related payments
        return request.user == obj.invoice.contract.client or request.user == obj.invoice.contract.contractor
    

class IsContractorOrClientForContract(BasePermission):
    def has_object_permission(self, request, view, obj):
        # Assuming `obj` is a Contract object
        return request.user == obj.client or request.user == obj.contractor
    

class IsClientOrReadOnly(BasePermission):
    """
    Clients can view contractors (read-only).
    They can view their own invoices (write access limited to admins).
    """
    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True  # Allow read-only access
        # Only allow clients to view their own invoices
        return request.user == obj.client.user
    

class IsContractorOrReadOnly(BasePermission):
    """
    Contractors can update their own data and view associated clients.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True  # Allow read-only access
        # Only allow contractors to edit their own profile
        return request.user == obj.user
    
class IsAdminUser(BasePermission):
    """
    Admins have full access.
    """
    def has_permission(self, request, view):
        return request.user.is_staff  # Check if the user is marked as an admin/staff.