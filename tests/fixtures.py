import copy

def seed():
    records=[]
    for rid,topic,statement in [("role","Role","Synthetic user's project role"),
                                ("language","Language","Synthetic user prefers 中文")]:
        records.append({"id":rid,"topic":topic,"statement":statement,"use":"Use only for the synthetic test",
                        "scope":"global","status":"confirmed","reviewed_on":"2026-01-01",
                        "evidence":[{"kind":"direct_user","reference":"synthetic-"+rid,"summary":"Synthetic fixture"}]})
    return {"schema_version":1,"revision":0,"updated_at":"2026-01-01T00:00:00+00:00",
            "records":records,"history":[],"last_change":{"operation":"seed","ids":[r["id"] for r in records],"reason":"Synthetic fixture"}}
