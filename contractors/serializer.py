from rest_framework import serializers
from .models import Contractor, Contract, Client, Invoice, Payment, Message, Conversation


# Serializer for Contractor model
class ContractorSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username') 
    
    class Meta:
        model = Contractor
        fields = '__all__'  # This will include all fields from the Contractor model

# Serializer for Contract model
class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = '__all__'  # This will include all fields from the Contract model

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        
    def validate_amount_paid(self, value):
        if value < 0:
            raise serializers.ValidationError("The amount paid cannot be negative.")
        return value
    

class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_name', 'content', 'timestamp']
