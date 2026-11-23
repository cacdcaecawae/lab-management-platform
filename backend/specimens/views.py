import logging
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.exceptions import Conflict
from core.files import download
from core.history import serialize_history
from core.notifications import notify
from core.permissions import IsActiveMember, IsManager, is_manager, is_supervisor, scope_group

from .models import Defect, Specimen, SpecimenLoan
from .queries import open_loans, overdue_loans
from .serializers import LoanSerializer, ReturnSerializer, SpecimenSerializer

logger = logging.getLogger(__name__)


class SpecimenViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Group-wide read; only managers create and edit. No delete: a specimen no longer used gets status=retired.
    Anyone in the group borrows an available specimen for themselves; the borrower or a manager returns it."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = SpecimenSerializer
    filter_backends = [SearchFilter]
    # Not the defects: searching them would let a student test guesses at a blind test's answer.
    search_fields = ["code", "name", "material", "location"]

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        defects = Defect.objects.all()
        if not is_supervisor(self.request.user):
            # The prefetch is a second query: it checks the flag itself, or a manager switching back to a blind test
            # in between would send the new values under the "public" flag read by the first.
            defects = defects.filter(specimen__defects_public=True)
        prefetches = [
            Prefetch("defects", queryset=defects),
            Prefetch("loans", queryset=open_loans().select_related("borrower", "project"), to_attr="open_loans"),
        ]
        if self.action != "list":
            prefetches.append(
                Prefetch(
                    "loans",
                    queryset=SpecimenLoan.objects.exclude(return_photo="")
                    .select_related("returned_by")
                    .order_by("-returned_at", "-id"),
                    to_attr="photo_loans",
                )
            )
        specimens = scope_group(
            Specimen.objects.select_related("custodian").prefetch_related(*prefetches),
            self.request.user,
        )
        params = self.request.query_params
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return specimens
        if params.get("kind"):
            specimens = specimens.filter(kind=params["kind"])
        if params.get("status"):
            specimens = specimens.filter(status=params["status"])
        loans = open_loans().filter(specimen=OuterRef("pk"))
        if params.get("overdue") == "1":
            loans = overdue_loans(loans)
        if params.get("mine") == "1":
            loans = loans.filter(borrower=self.request.user)
        if any(params.get(key) == "1" for key in ("on_loan", "mine", "overdue")):
            specimens = specimens.filter(Exists(loans))
        return specimens

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))

    @action(detail=True)
    def loans(self, request, pk=None):
        loans = self.get_object().loans.select_related("borrower", "project", "returned_by")
        page = self.paginate_queryset(loans)
        return self.get_paginated_response(LoanSerializer(page, many=True).data)

    @action(detail=True, methods=["post"])
    def borrow(self, request, pk=None):
        body = LoanSerializer(data=request.data, context=self.get_serializer_context())
        body.is_valid(raise_exception=True)
        specimen = self.get_object()
        with transaction.atomic():
            locked = Specimen.objects.select_for_update().get(pk=specimen.pk)  # one borrow or status change at a time
            if locked.status != Specimen.Status.AVAILABLE:
                raise Conflict(f"试件状态是“{locked.get_status_display()}”，不能借出", code="not_available")
            if open_loans().filter(specimen=locked).exists():
                raise Conflict("试件已经借出，归还后才能再借", code="on_loan")
            try:
                with transaction.atomic():
                    loan = body.save(specimen=locked, borrower=request.user)
            except IntegrityError:  # the database constraint, should the check above ever be bypassed
                raise Conflict("试件已经借出，归还后才能再借", code="on_loan") from None
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="return")
    def return_loan(self, request, pk=None):
        body = ReturnSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        specimen = self.get_object()
        loan = None
        photo_saved = False
        committed = False

        def mark_committed():
            nonlocal committed
            committed = True

        try:
            with transaction.atomic():
                # Lock Specimen first, matching borrow() and SpecimenSerializer.update() lock order.
                locked = Specimen.objects.select_for_update().get(pk=specimen.pk)
                loan = open_loans().select_for_update().filter(specimen=locked).first()
                if loan is None:
                    raise Conflict("试件没有借出", code="not_on_loan")
                if loan.pk != body.validated_data["loan_id_seen"]:
                    raise Conflict("借用记录已变化，请刷新后重新核对", code="stale_loan")
                if loan.borrower_id != request.user.id and not is_manager(request.user):
                    raise PermissionDenied("只有借用人或管理员能登记归还")
                now = timezone.now()
                loan.returned_at = now
                loan.returned_by = request.user
                loan.return_note = body.validated_data["note"].strip()
                location = body.validated_data["return_location"].strip()
                loan.return_location = location
                if photo := body.validated_data.get("photo"):
                    loan.return_photo = photo
                    loan.return_photo_size = photo.size
                    loan.return_photo_uploaded_at = now
                    photo_saved = True
                loan.save()
                transaction.on_commit(mark_committed)
                if location and location != locked.location:
                    locked.location = location
                    locked._change_reason = f"{request.user.display_name} 归还时更新存放位置"
                    locked.save()
                if loan.borrower_id != request.user.id:
                    notify(locked.group_id, "管理员已登记试件归还", f"/specimens/{locked.pk}", recipient_ids=[loan.borrower_id])
        except Exception:
            if not committed and photo_saved and loan and loan.return_photo and loan.return_photo._committed:
                try:
                    loan.return_photo.delete(save=False)
                except Exception:
                    logger.exception("Failed to clean up rolled-back specimen return photo %s", loan.return_photo.name)
            raise
        return Response(LoanSerializer(loan).data)

    @action(detail=True, url_path=r"loans/(?P<loan_id>\d+)/photo")
    def loan_photo(self, request, pk=None, loan_id=None):
        specimen = self.get_object()
        loan = SpecimenLoan.objects.filter(specimen=specimen, pk=loan_id).first()
        if not (loan and loan.return_photo):
            raise NotFound()
        try:
            return download(loan.return_photo, Path(loan.return_photo.name).name)
        except FileNotFoundError:
            raise NotFound() from None
