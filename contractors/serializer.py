from rest_framework import serializers
from .models import Contractor, Contract, Client, Invoice, Payment, Message, Conversation,User, Tutorials


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


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_name', 'content', 'timestamp']

class ConversationSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField()
    latest_message = serializers.SerializerMethodField("get_latest_message")
    latest_message_timestamp = serializers.DateTimeField(
        source="messages.last.timestamp", read_only=True
    )

    class Meta:
        model = Conversation
        fields = ["id", "participants", "latest_message", "latest_message_timestamp"]

    def get_participants(self, obj):
        return [user.username for user in obj.participants.all()]

    def get_latest_message(self, obj):
        last_message = obj.messages.last()  # Retrieve the most recent message
        return last_message.content if last_message else "No messages yet."
    


class ServiceRequestSerializer(serializers.Serializer):
    searchText = serializers.CharField(
        max_length=500, 
        required=True, 
        error_messages={
            'blank': 'Service request cannot be empty.',
            'null': 'Service request is required.',
            'max_length': 'Service request is too long (max 500 characters).'
        }
    )

class SendContractSerializer(serializers.Serializer):
    contractId = serializers.IntegerField()
    clientUsername = serializers.CharField()

    def validate(self, data):
        # Validate contract existence
        try:
            data['contract'] = Contract.objects.get(id=data['contractId'])
        except Contract.DoesNotExist:
            raise serializers.ValidationError({"contractId": "Contract not found."})

        # Validate client existence
        try:
            data['client'] = User.objects.get(username=data['clientUsername'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"clientUsername": "Client not found."})

        return data
    
class TutorialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutorials
        fields = '__all__' # This will include all fields from the Tutorials model