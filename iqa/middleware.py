from django.http import HttpResponse


class HealthCheckMiddleware:
    """Answer /healthz before Django validates the Host header.

    App Runner's load-balancer health check requests /healthz with a Host
    header set to the container's private IP, which is deliberately not in
    ALLOWED_HOSTS. Handling the probe here (using only request.path, which
    needs no host resolution) lets the check pass while ALLOWED_HOSTS stays
    strict for all real traffic.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/healthz':
            return HttpResponse('ok', content_type='text/plain')
        return self.get_response(request)
