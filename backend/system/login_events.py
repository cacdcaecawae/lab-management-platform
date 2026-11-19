from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView

from accounts.models import LoginEvent
from core.pagination import Pagination
from core.permissions import IsSuperuser


class LoginEventQuery(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False)
    outcome = serializers.ChoiceField(choices=LoginEvent.Outcome.values, required=False)
    from_at = serializers.DateTimeField(required=False)
    to_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if "from_at" in attrs and "to_at" in attrs and attrs["from_at"] >= attrs["to_at"]:
            raise serializers.ValidationError({"to_at": "结束时间须晚于开始时间"})
        return attrs


class LoginEventsView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        params = request.query_params
        values = {"username": "username", "outcome": "outcome", "from": "from_at", "to": "to_at"}
        filters = LoginEventQuery(data={field: params[key] for key, field in values.items() if key in params})
        filters.is_valid(raise_exception=True)
        selected = filters.validated_data
        now = timezone.now()
        visible = LoginEvent.objects.filter(at__gte=now - timedelta(days=180))
        query = visible
        for key, lookup in (
            ("username", "user__username"), ("outcome", "outcome"), ("from_at", "at__gte"), ("to_at", "at__lt"),
        ):
            if key in selected:
                query = query.filter(**{lookup: selected[key]})
        pager = Pagination()
        page = pager.paginate_queryset(query.select_related("user"), request)
        response = pager.get_paginated_response([
            {"id": row.pk, "at": row.at, "outcome": row.outcome,
             "account": {"id": row.user_id, "username": row.user.username} if row.user else None, "ip": row.ip}
            for row in page
        ])
        response.data["audit_enabled"] = settings.LOGIN_AUDIT_ENABLED
        response.data["top_failed_24h"] = list(
            visible.filter(at__gte=now - timedelta(hours=24), outcome=LoginEvent.Outcome.FAILED, user__isnull=False)
            .order_by().values("user_id", "user__username").annotate(failures=Count("pk"))
            .order_by("-failures", "user_id")[:5]
        )
        return response
