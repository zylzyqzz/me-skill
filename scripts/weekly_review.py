"""Validate a retrospective collected by the host AI after a scheduled trigger.

This module never crawls conversations or infers habits on its own.
"""
from datetime import datetime, timedelta, timezone

from profile_store import require


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timestamp needs a timezone")
    return result.astimezone(timezone.utc)


def window(now=None):
    end = now or datetime.now(timezone.utc)
    require(end.tzinfo is not None, "Trigger needs a timezone")
    end = end.astimezone(timezone.utc).replace(microsecond=0)
    return {"period_start": (end - timedelta(days=7)).isoformat(),
            "period_end": end.isoformat()}


def strings(value, label, nonempty=False):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value),
            "Invalid " + label)
    require(not nonempty or bool(value), "Empty " + label)


def validate(review):
    require(isinstance(review, dict) and set(review) == {
        "period_start", "period_end", "coverage", "evidence", "activities", "habits", "profile_evidence"},
        "Unexpected review fields")
    start, end = timestamp(review["period_start"]), timestamp(review["period_end"])
    require(end - start == timedelta(days=7), "Review must cover the preceding seven days")
    coverage = review["coverage"]
    require(isinstance(coverage, dict) and set(coverage) == {
        "status", "sources", "sessions_reviewed", "limitations"}, "Invalid coverage fields")
    require(coverage["status"] in ("complete", "partial", "unavailable"), "Invalid coverage status")
    strings(coverage["sources"], "sources")
    strings(coverage["limitations"], "limitations", coverage["status"] != "complete")
    require(type(coverage["sessions_reviewed"]) is int and coverage["sessions_reviewed"] >= 0,
            "Invalid reviewed session count")
    require(coverage["status"] == "unavailable" or bool(coverage["sources"]), "Available history needs sources")
    require(isinstance(review["evidence"], list), "Invalid evidence list")
    evidence_ids = set()
    for evidence in review["evidence"]:
        require(isinstance(evidence, dict) and set(evidence) == {"id", "at", "source", "summary"},
                "Invalid review evidence")
        require(isinstance(evidence["id"], str) and evidence["id"].strip() and
                evidence["id"] not in evidence_ids, "Duplicate or invalid evidence id")
        evidence_ids.add(evidence["id"])
        require(start <= timestamp(evidence["at"]) < end, "Evidence outside review window")
        require(evidence["source"] in coverage["sources"], "Unknown evidence source")
        require(isinstance(evidence["summary"], str) and evidence["summary"].strip(), "Empty evidence summary")
    require(not evidence_ids or coverage["sessions_reviewed"] > 0, "Evidence needs reviewed sessions")

    def refs(value):
        strings(value, "evidence references", True)
        require(len(set(value)) == len(value) and set(value) <= evidence_ids, "Unknown or duplicate evidence reference")

    for category in ("activities", "habits"):
        require(isinstance(review[category], list), "Invalid review summary")
        for item in review[category]:
            keys = {"summary", "evidence_ids"} | ({"assessment"} if category == "habits" else set())
            require(isinstance(item, dict) and set(item) == keys, "Invalid summary fields")
            require(isinstance(item["summary"], str) and item["summary"].strip(), "Empty review summary")
            refs(item["evidence_ids"])
            if category == "habits":
                require(item["assessment"] in ("confirmed", "candidate", "unchanged"), "Invalid habit assessment")
    require(isinstance(review["profile_evidence"], dict), "Invalid profile evidence mapping")
    for record_id, evidence_refs in review["profile_evidence"].items():
        require(isinstance(record_id, str) and record_id.strip(), "Invalid profile record id")
        refs(evidence_refs)
    if coverage["status"] == "unavailable":
        require(not evidence_ids and coverage["sessions_reviewed"] == 0, "Unavailable history cannot contain evidence")
    return review


def render(review):
    coverage = review["coverage"]
    lines = [f"复盘区间：{review['period_start']} 至 {review['period_end']}（左闭右开，最近 7 天）",
             f"覆盖：{coverage['status']}；实际查看 {coverage['sessions_reviewed']} 个会话。",
             "来源：" + "、".join(coverage["sources"]), "", "### 本周使用情况"]
    lines += ["- " + x["summary"] + "（" + ", ".join(x["evidence_ids"]) + "）" for x in review["activities"]]
    lines += ["", "### 使用习惯与纠正"]
    lines += [f"- [{x['assessment']}] {x['summary']}（{', '.join(x['evidence_ids'])}）" for x in review["habits"]]
    if not review["habits"]:
        lines.append("- 未发现足以归纳的新习惯；不虚构偏好变化。")
    lines += ["", "### 覆盖限制"]
    lines += ["- " + x for x in coverage["limitations"]] or ["- 已覆盖声明的本安装可访问范围；不代表用户全部 AI 活动。"]
    return "\n".join(lines)
