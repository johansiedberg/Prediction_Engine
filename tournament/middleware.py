from django.http import Http404
from django.shortcuts import redirect

class EngineAdminPortMiddleware:
    """
    Middleware for Port 2029 Engine Admin Isolation:
    - Port 2029: Dedicated Engine Admin portal.
      - GET / -> Engine Admin Root (Dashboard if logged in as admin, Login form if not).
      - POST /login/ or POST / -> Engine Admin Login handler.
      - POST /logout/ -> Engine Admin Logout handler.
      - /engine-admin/... -> Engine Admin AJAX endpoints.
      - All other paths on port 2029 -> Redirect to /.
    - Port 2028 (or non-2029): Player Application.
      - Access to /engine-admin/ raises Http404.
      - /pool-admin/... -> Pool Admin Portal (accessible only on port 2028).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host_parts = request.get_host().split(':')
        port = host_parts[1] if len(host_parts) > 1 else str(request.get_port())
        path = request.path

        if port == '2029':
            if path == '/' or path == '/login/':
                if request.method == 'POST':
                    from tournament.views.engine_admin import engine_admin_login_view
                    return engine_admin_login_view(request)
                else:
                    from tournament.views.engine_admin import engine_admin_root_view
                    return engine_admin_root_view(request)
            elif path == '/logout/':
                from tournament.views.engine_admin import engine_admin_logout_view
                return engine_admin_logout_view(request)
            elif path.startswith('/engine-admin/'):
                return self.get_response(request)
            elif path.startswith('/static/') or path.startswith('/media/'):
                return self.get_response(request)
            else:
                return redirect('/')
        else:
            if path.startswith('/engine-admin/'):
                raise Http404("Engine Admin does not exist on this port.")

        return self.get_response(request)
