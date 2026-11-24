"""Values the group already uses in a free-text column, so forms can suggest them (A302, not A-302 next to 302室).
Only suggests: any other text is still accepted where the value is saved."""
from collections import Counter

from django.db.models import Count
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from achievements.models import Achievement
from core.params import search_text
from core.permissions import IsActiveMember, scope_group
from equipment.models import Equipment
from inventory.models import Consumable
from knowledge.models import Doc
from specimens.models import Specimen

LIMIT = 20

# Every one is read group-wide on its own list, so the values carry no more than the list shows.
FIELDS = {
    "equipment.category": (Equipment.objects, "category"),
    "equipment.location": (Equipment.objects, "location"),
    "specimen.material": (Specimen.objects, "material"),
    "specimen.location": (Specimen.objects, "location"),
    "consumable.category": (Consumable.objects, "category"),
    "consumable.location": (Consumable.objects, "location"),
    "consumable.unit": (Consumable.objects, "unit"),
    "member.research_direction": (User.objects.filter(pending=False), "research_direction"),
    "achievement.venue": (Achievement.objects, "venue"),
    "doc.tags": (Doc.objects, "tags"),
}


class SuggestionsView(APIView):
    """GET /api/suggestions/<field>/?search= → the most used values first, at most 20, spelled exactly as stored."""

    permission_classes = [IsActiveMember]

    def get(self, request, field):
        if field not in FIELDS:
            raise NotFound()
        source, column = FIELDS[field]
        keyword = search_text(request.query_params)
        rows = scope_group(source.all(), request.user)
        if column == "tags":  # an array: counted here (one group's documents) rather than unnested in SQL
            counts = Counter(tag for tags in rows.values_list("tags", flat=True) for tag in tags)
            values = [tag for tag, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if keyword.lower() in tag.lower()]
            return Response(values[:LIMIT])
        rows = rows.exclude(**{column: ""})
        if keyword:
            rows = rows.filter(**{f"{column}__icontains": keyword})
        counted = rows.values(column).annotate(uses=Count("pk")).order_by("-uses", column)[:LIMIT]
        return Response([row[column] for row in counted])
