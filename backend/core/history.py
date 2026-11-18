"""Serialize django-simple-history records for the /history/ endpoints.

To record why a change happened (e.g. a supervisor returning a record), set
`obj._change_reason = "..."` before `obj.save()`; it shows up as `reason`."""


def serialize_history(instance):
    records = list(instance.history.select_related("history_user").order_by("history_date", "history_id"))
    result, previous = [], None
    names = {}  # (model, pk) -> label, so a value that recurs is looked up once
    for record in records:
        changes = []
        if previous is not None:
            delta = record.diff_against(previous)
            changes = [
                {"field": c.field, "old": _value(instance, c.field, c.old, names), "new": _value(instance, c.field, c.new, names)}
                for c in delta.changes
            ]
        user = record.history_user
        result.append(
            {
                "id": record.history_id,
                "date": record.history_date.isoformat(),
                "type": {"+": "created", "~": "changed", "-": "deleted"}[record.history_type],
                "user": {"id": user.id, "name": user.display_name} if user else None,
                "reason": record.history_change_reason or "",
                "changes": changes,
            }
        )
        previous = record
    return list(reversed(result))  # newest first


def _value(instance, field_name, value, names):
    """Foreign keys are stored as ids; show the object's name instead (members by display name, never the
    student id). An id whose object is gone stays an id."""
    field = instance._meta.get_field(field_name)
    if value is None or not field.many_to_one:
        return _plain(value)
    key = (field.related_model, value)
    if key not in names:
        obj = field.related_model._default_manager.filter(pk=value).first()
        names[key] = value if obj is None else getattr(obj, "display_name", None) or str(obj)
    return names[key]


def _plain(value):
    return value if isinstance(value, (str, int, float, bool, type(None), list, dict)) else str(value)
