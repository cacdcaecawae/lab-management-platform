from functools import reduce
from operator import or_

from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .permissions import scope_group


# ?module= : the sidebar's groups, told apart by where a notification links to (no column to migrate old ones).
MODULE_PATHS = {
    "projects": ("/projects",),
    "research": ("/experiments", "/runs", "/datasets"),
    "reports": ("/reports", "/meetings"),
    "lab": ("/equipment", "/bookings", "/specimens", "/consumables"),
    "money": ("/purchases", "/reimbursements", "/funds"),
    "members": ("/members",),
}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "link", "created_at", "read_at"]


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        user = self.request.user
        scoped = scope_group(Notification.objects.filter(recipient=user), user)
        scoped = scoped.filter(audience_role__in=user.audiences)  # a tag taken away hides what it brought
        params = self.request.query_params
        if self.action == "list" and params.get("unread") == "1":
            scoped = scoped.filter(read_at__isnull=True)
        if self.action == "list" and (module := params.get("module")):
            paths = MODULE_PATHS.get(module)
            scoped = scoped.filter(reduce(or_, (Q(link__startswith=p) for p in paths))) if paths else scoped.none()
        return scoped

    @action(detail=False, url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        obj = self.get_object()
        self.get_queryset().filter(pk=obj.pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        now = timezone.now()
        updated = self.get_queryset().filter(read_at__isnull=True, created_at__lte=now).update(read_at=now)
        return Response({"updated": updated})
