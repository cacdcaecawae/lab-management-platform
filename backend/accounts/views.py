import hashlib
from pathlib import Path

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import transaction
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from core.exceptions import Conflict
from core.files import checked_upload, delete_name_on_commit, download
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
        with transaction.atomic():
            # Locked by its code: closing or replacing the link waits for this application, or it no longer matches.
            # One application at a time per group, for the cap. Checked before the form, so without a valid link
            # nobody can probe which student numbers exist.
            group = ResearchGroup.objects.select_for_update().filter(signup_code=code).first() if isinstance(code, str) and code else None
            if group is None:
                raise ValidationError({"code": "注册链接已失效，请向课题组管理员要新的链接"})
            data = RegisterSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            if User.objects.filter(group=group, pending=True).count() >= PENDING_LIMIT:
                raise Conflict("待审核的申请太多，请联系课题组管理员先处理", code="too_many_pending")
            user = data.save(group=group)
            notify(group.pk, f"{user.name} 申请加入课题组，请审核", "/members", role="manager")
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

    def patch(self, request):
        if request.user.must_change_password:
            raise PermissionDenied(detail="请先修改初始密码", code="password_change_required")
        data = MeSerializer(request.user, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)


AVATAR_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
AVATAR_MAX_SIZE = 2 * 1024**2


class AvatarView(APIView):
    """The person's own picture. The page crops it to a 256px square JPEG before uploading, so no image library here;
    only picture extensions are kept and they are served as pictures (nosniff), never as a page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.avatar:
            raise NotFound()
        response = download(request.user.avatar, Path(request.user.avatar.name).name)
        # avatar_url carries ?v=<uuid> which changes on every upload; cache privately to avoid refetching on every page.
        response["Cache-Control"] = "private, max-age=86400"
        return response

    def post(self, request):
        if request.user.must_change_password:
            raise PermissionDenied(detail="请先修改初始密码", code="password_change_required")
        uploaded, name = checked_upload(request, AVATAR_MAX_SIZE, AVATAR_TYPES)
        with transaction.atomic():
            # Locked: two uploads at once replace one another instead of orphaning a file.
            user = User.objects.select_for_update().get(pk=request.user.pk)
            storage, old_name = user.avatar.storage, user.avatar.name
            user.avatar.save(name, uploaded, save=False)
            try:
                with transaction.atomic():
                    user.save(update_fields=["avatar"])
                    if old_name:
                        delete_name_on_commit(storage, old_name)
            except Exception:
                storage.delete(user.avatar.name)
                raise
        return Response(MeSerializer(user).data)


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
