"""A collection's rules as rows a person edits, and the sentence they read as.

A row is a field, how it is asked and what for. The wire keeps criteria per axis; this
turns one into the other both ways, reading the fields off the registry's own axes, so
an axis the registry adds arrives here as a field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.games.collection_filters import UNCONSTRAINED
from common.i18n import t

# How a row asks of its field. Held in the draft only; the wire never sees these.
ANY_OF = "any_of"
STARTS_WITH = "starts_with"
BETWEEN = "between"
BEFORE = "before"
AFTER = "after"
AT_LEAST = "at_least"
EXACTLY = "exactly"
YES = "yes"
NO = "no"

OPERATOR_WORDS = {
    ANY_OF: "console.collection_rules.is_any_of",
    STARTS_WITH: "console.collection_rules.starts_with",
    BETWEEN: "console.collection_rules.between",
    BEFORE: "console.collection_rules.before",
    AFTER: "console.collection_rules.after",
    AT_LEAST: "console.collection_rules.at_least",
    EXACTLY: "console.collection_rules.is_exactly",
}

# A flag's two answers in the sentence, where it has words of its own.
FLAG_WORDS = {
    "played": {YES: "console.collection_rules.you_played",
               NO: "console.collection_rules.you_never_played"},
    "favorite": {YES: "console.collection_rules.you_marked_favorite",
                 NO: "console.collection_rules.you_not_marked_favorite"},
}


@dataclass(frozen=True)
class Field:
    """One thing a row can be about: an axis, and the axes asked under it."""

    name: str
    label: str
    summary: str
    kind: str
    values: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    # The axis holding this field's range, and the one reading it as a floor.
    ranged: str = ""
    floored: str = ""

    @property
    def askable(self) -> bool:
        """Whether a row on it can ask for anything in this library."""
        return bool(self.values or self.ranged or self.kind == "flag")

    @property
    def operators(self) -> list[str]:
        """What a row on this field can ask, the one a new row takes first."""
        if self.kind == "flag":
            return [YES, NO]
        if self.kind == "letter":
            return [STARTS_WITH]
        if self.kind == "rating":
            return [AT_LEAST, EXACTLY] if self.floored else [EXACTLY]
        return [BETWEEN, BEFORE, AFTER, ANY_OF] if self.ranged else [ANY_OF]


def fields(axes: list[dict[str, Any]]) -> list[Field]:
    """The fields a row can be about, in the registry's order."""
    ranged = {str(one.get("field") or ""): str(one.get("name") or "") for one in axes
              if one.get("field") and one.get("kind") == "range"}
    floored = {str(one.get("field") or ""): str(one.get("name") or "") for one in axes
               if one.get("field") and one.get("kind") == "rating"}
    return [Field(name=str(one.get("name") or ""), label=str(one.get("label") or ""),
                  summary=str(one.get("summary") or ""), kind=str(one.get("kind") or ""),
                  values=[str(value) for value in one.get("values") or []],
                  counts=dict(one.get("counts") or {}),
                  ranged=ranged.get(str(one.get("name") or ""), ""),
                  floored=floored.get(str(one.get("name") or ""), ""))
            for one in axes if not one.get("field")]


def by_name(known: list[Field]) -> dict[str, Field]:
    return {one.name: one for one in known}


def row_on(chosen: Field) -> dict[str, Any]:
    """A row on this field, asking what the field asks first, of nothing yet."""
    return {"field": chosen.name, "op": chosen.operators[0], "value": None}


def _chosen(value: Any) -> list[str]:
    """A criterion as the values it names. "All" names none."""
    if isinstance(value, list):
        named = [str(one).strip() for one in value]
    else:
        named = [part.strip() for part in str(value or "").split(",")]
    return [one for one in named if one and one != UNCONSTRAINED]


def rows_from(filters: dict[str, Any] | None, known: list[Field]) -> list[dict[str, Any]]:
    """The rows a stored rule reads as, one per field it sets, in the registry's order."""
    filters = filters or {}
    rows: list[dict[str, Any]] = []
    for one in known:
        if one.ranged:
            start, end = _ends(filters.get(one.ranged))
            if start is not None and end is not None:
                rows.append({"field": one.name, "op": BETWEEN,
                             "value": {"from": start, "to": end}})
            elif end is not None:
                rows.append({"field": one.name, "op": BEFORE, "value": end + 1})
            elif start is not None:
                rows.append({"field": one.name, "op": AFTER, "value": start - 1})
        if one.kind == "flag":
            said = filters.get(one.name)
            if said is not None:
                rows.append({"field": one.name, "op": YES if said else NO, "value": None})
            continue
        named = _chosen(filters.get(one.name))
        if not named:
            continue
        if one.kind == "rating":
            floor = bool(one.floored and filters.get(one.floored))
            rows.append({"field": one.name, "op": AT_LEAST if floor else EXACTLY,
                         "value": named[0]})
        else:
            rows.append({"field": one.name,
                         "op": STARTS_WITH if one.kind == "letter" else ANY_OF,
                         "value": named})
    return rows


def _ends(value: Any) -> tuple[int | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    return _year(value.get("from")), _year(value.get("to"))


def _year(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def complete(row: dict[str, Any]) -> bool:
    """Whether a row asks for something yet."""
    op, value = row.get("op"), row.get("value")
    if op in (YES, NO):
        return bool(row.get("field"))
    if op in (ANY_OF, STARTS_WITH):
        return bool(_chosen(value))
    if op == BETWEEN:
        start, end = _ends(value)
        return start is not None and end is not None
    if op in (BEFORE, AFTER):
        return _year(value) is not None
    if op in (AT_LEAST, EXACTLY):
        return bool(_chosen(value))
    return False


def filters_from(rows: list[dict[str, Any]], known: list[Field]) -> dict[str, Any]:
    """The criteria the rows ask for, in the shape the wire takes. A row that asks for
    nothing yet adds nothing."""
    named = by_name(known)
    said: dict[str, Any] = {}
    for row in rows:
        one = named.get(str(row.get("field") or ""))
        if one is None or not complete(row):
            continue
        op, value = row["op"], row.get("value")
        if op in (YES, NO):
            said[one.name] = op == YES
        elif op in (ANY_OF, STARTS_WITH):
            said[one.name] = _chosen(value)
        elif op in (AT_LEAST, EXACTLY):
            said[one.name] = _chosen(value)[0]
            if one.floored:
                said[one.floored] = op == AT_LEAST
        elif op == BETWEEN and one.ranged:
            start, end = _ends(value)
            if start is not None and end is not None:
                start, end = min(start, end), max(start, end)
            said[one.ranged] = {"from": start, "to": end}
        elif op in (BEFORE, AFTER) and one.ranged:
            year = _year(value) or 0
            said[one.ranged] = {"to": year - 1} if op == BEFORE else {"from": year + 1}
    return said


def operator_word(op: str) -> str:
    """What an operator is called on a row."""
    if op in (YES, NO):
        return t("word.yes") if op == YES else t("word.no")
    return t(OPERATOR_WORDS.get(op, ""))


def sentence(rows: list[dict[str, Any]], known: list[Field],
             added: int = 0, taken: int = 0) -> str:
    """The rule in words, with its connectives showing."""
    named = by_name(known)
    clauses = [said for said in (_clause(row, named) for row in rows if complete(row))
               if said]
    if not clauses:
        return t("console.collection_rules.add_rule_choose_games")
    joined = _all_of(clauses)
    if added and taken:
        return t("console.collection_rules.every_game_where_plus_minus", clauses=joined,
                 added=added, taken=taken)
    if added:
        return t("console.collection_rules.every_game_where_plus", clauses=joined,
                 added=added)
    if taken:
        return t("console.collection_rules.every_game_where_minus", clauses=joined,
                 taken=taken)
    return t("console.collection_rules.every_game_where", clauses=joined)


def _clause(row: dict[str, Any], named: dict[str, Field]) -> str:
    one = named.get(str(row.get("field") or ""))
    if one is None:
        return ""
    op, value = row["op"], row.get("value")
    if op in (YES, NO):
        flag = FLAG_WORDS.get(one.name, {}).get(op)
        if flag:
            return t(flag)
        return t("console.collection_rules.axis_is", axis=one.label,
                 values=t("word.yes") if op == YES else t("word.no"))
    if op == STARTS_WITH:
        return t("console.collection_rules.title_starts_with",
                 values=_either(_chosen(value)))
    if op == ANY_OF:
        return t("console.collection_rules.axis_is", axis=one.label,
                 values=_either(_chosen(value)))
    if op in (AT_LEAST, EXACTLY):
        stars = t("console.stars.5", n=_chosen(value)[0])
        if op == AT_LEAST:
            return t("console.collection_rules.axis_at_least", axis=one.label, value=stars)
        return t("console.collection_rules.axis_is", axis=one.label, values=stars)
    if op == BETWEEN:
        start, end = _ends(value)
        low, high = min(start or 0, end or 0), max(start or 0, end or 0)
        return t("console.collection_rules.axis_between", axis=one.label,
                 start=low, end=high)
    if op == BEFORE:
        return t("console.collection_rules.axis_before", axis=one.label, value=value)
    if op == AFTER:
        return t("console.collection_rules.axis_after", axis=one.label, value=value)
    return ""


def _either(values: list[str]) -> str:
    quoted = [f"“{value}”" for value in values]
    if len(quoted) == 1:
        return quoted[0]
    return t("console.collection_rules.or_last",
             rest=t("console.collection_rules.list_join").join(quoted[:-1]),
             last=quoted[-1])


def _all_of(clauses: list[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    return t("console.collection_rules.and_last",
             rest=t("console.collection_rules.list_join").join(clauses[:-1]),
             last=clauses[-1])
