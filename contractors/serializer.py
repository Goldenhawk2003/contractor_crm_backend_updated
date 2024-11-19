from rest_framework import serializers
from .models import Contractor, Contract, Client, Invoice, Payment, Message


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
    class Meta:
        model = Message
        fields = ['id', 'sender', 'receiver', 'message', 'timestamp']

    # You may want to add some custom validation to ensure users can only message each other if certain conditions apply
    def validate(self, data):
        if data['sender'] == data['receiver']:
            raise serializers.ValidationError("You cannot send a message to yourself.")
        return data