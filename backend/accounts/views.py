import hashlib

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .login_audit import record_attempt, record_throttle_minute, source_address
from .serializers import LoginSerializer, MeSerializer, PasswordChangeSerializer


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the csrftoken cookie. The SPA calls this once before the first POST."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginRateThrottle(SimpleRateThrottle):
    """Per account and address. Not per address alone: a whole lab may share one campus NAT address. Not per account
    alone: anyone could then keep someone locked out by failing on their (predictable) student number. The address is
    the one Nginx appends to X-Forwarded-For (REST_FRAMEWORK NUM_PROXIES). Counts live in the database cache, shared
    by every Gunicorn worker."""

    rate = "5/min"

    def get_ident(self, request):
        return source_address(request) or ""

    def get_cache_key(self, request, view):
        username = request.data.get("username", "") if isinstance(request.data, dict) else ""
        key = f"{str(username).strip().lower()}|{self.get_ident(request)}"
        return "throttle_login_" + hashlib.sha256(key.encode()).hexdigest()


# DRF only checks CSRF for already-authenticated sessions; protect login too (login CSRF).
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def throttled(self, request, wait):
        record_throttle_minute()
        super().throttled(request, wait)

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            record_attempt(request, candidate=data.validated_data["username"])
            raise AuthenticationFailed("用户名或密码错误", code="invalid_credentials")
        login(request, user)
        record_attempt(request, user=user)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]  # allowed even before the initial password is changed

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = PasswordChangeSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        user = request.user
        user.set_password(data.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)
