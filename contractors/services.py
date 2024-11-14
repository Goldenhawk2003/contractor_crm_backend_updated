from .models import ClientQuizResponse, Contractor


class QuizMatchService:

    def match_client_to_contractor(self, client):
        # Get all the client's responses
        responses = ClientQuizResponse.objects.filter(client=client)
        
        # Collect all job types from the responses
        job_types = set(response.selected_answer.job_type for response in responses)
        
        # Find contractors that match any of the job types from the quiz responses
        matched_contractors = Contractor.objects.filter(job_type__in=job_types)
        
        return matched_contractors