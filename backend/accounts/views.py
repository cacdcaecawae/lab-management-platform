import hashlib

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import transaction
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from core.exceptions import Conflict
from core.notifications import notify

from .login_audit import record_attempt, record_throttle_minute, source_address
from .member_serializers import RegisterSerializer
from .models import ResearchGroup, User
from .serializers import LoginSerializer, MeSerializer, PasswordChangeSerializer

PENDING_LIMIT = 30  # per group: a leaked link cannot bury the managers in applications


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
            # Only someone who knows the password learns that the account is waiting.
            waiting = User.objects.filter(username=data.validated_data["username"], pending=True).first()
            if waiting and waiting.check_password(data.validated_data["password"]):
                raise PermissionDenied("账号正在等待管理员审核，通过后才能登录", code="pending_approval")
            raise AuthenticationFailed("用户名或密码错误", code="invalid_credentials")
        login(request, user)
        record_attempt(request, user=user)
        return Response(MeSerializer(user).data)


class RegisterRateThrottle(SimpleRateThrottle):
    """Per source address, as LoginRateThrottle sees it."""

    rate = "10/hour"

    def get_cache_key(self, request, view):
        return "throttle_register_" + hashlib.sha256((source_address(request) or "").encode()).hexdigest()


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    """A student applies through their group's link: an inactive, pending account the group's managers approve."""

    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        code = request.data.get("code") if isinstance(request.data, dict) else None
        # Checked before the form, so without a valid link nobody can probe which student numbers exist.
        group = ResearchGroup.objects.filter(signup_code=code).first() if isinstance(code, str) and code else None
        if group is None:
            raise ValidationError({"code": "注册链接已失效，请向课题组管理员要新的链接"})
        data = RegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            ResearchGroup.objects.select_for_update().get(pk=group.pk)  # one application at a time per group, for the cap
            if User.objects.filter(group=group, pending=True).count() >= PENDING_LIMIT:
                raise Conflict("待审核的申请太多，请联系课题组管理员先处理", code="too_many_pending")
            user = data.save(group=group)
            notify(group.pk, f"{user.name} 申请加入课题组，请审核", "/members", role=User.Role.MANAGER)
        return Response(status=status.HTTP_201_CREATED)


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
