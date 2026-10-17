class ClinicalPrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(('/submit-patient-details/', '/doctor/', '/photos/', '/admin/')):
            response['Cache-Control'] = 'no-store, private'
            response['Pragma'] = 'no-cache'
            response['X-Robots-Tag'] = 'noindex, nofollow'
        response['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
        return response
