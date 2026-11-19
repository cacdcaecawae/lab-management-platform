"""Read-only operational view; the web process cannot mount storage."""
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from core.nas_storage import nas_ready
from core.permissions import IsSuperuser


class StorageView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        nas = bool(settings.LAB_NAS_STORAGE_ID)
        return Response({
            "primary": "nas" if nas else "local",
            "nas_ready": nas_ready(settings.MEDIA_ROOT) if nas else None,
        })
