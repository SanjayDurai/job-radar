"""Master resume: validate resume/master.yaml and store it in the database (app_state 'resume_master').

The dashboard reads it from there to tailor resumes, so your personal details never go into git.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.models import AppState
from radar.settings import REPO_ROOT

MASTER_PATH = REPO_ROOT / "resume" / "master.yaml"
STATE_KEY = "resume_master"


class ResumeError(ValueError):
    pass


def load_master(path: Path = MASTER_PATH) -> dict[str, Any]:
    if not path.exists():
        raise ResumeError(f"{path} not found. Create it from your resume (see README, 'Tailored resumes').")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise ResumeError(
            f"master.yaml isn't valid YAML{where}: {getattr(e, 'problem', e)}. "
            'Tip: put text that contains a colon in "double quotes".'
        ) from e
    validate_master(data)
    return data


def validate_master(m: dict[str, Any]) -> None:
    errors: list[str] = []
    basics = m.get("basics") or {}
    for key in ("name", "email"):
        if not basics.get(key):
            errors.append(f"basics.{key} is required")
    if not isinstance(m.get("skills"), dict) or not m["skills"]:
        errors.append("skills must be a group -> [skills] mapping")
    ids: set[str] = set()
    for section in ("experience", "projects"):
        for entry in m.get(section) or []:
            if not entry.get("id"):
                errors.append(f"every {section} entry needs an id")
            for b in entry.get("bullets") or []:
                bid = b.get("id") if isinstance(b, dict) else None
                if not bid or not b.get("text"):
                    errors.append(f"{section} '{entry.get('id')}': every bullet needs an id and text")
                elif bid in ids:
                    errors.append(f"duplicate bullet id '{bid}'")
                else:
                    ids.add(bid)
    if not m.get("experience"):
        errors.append("experience is required")
    if errors:
        raise ResumeError("master.yaml problems:\n  " + "\n  ".join(errors))


def upload_master(session: Session, master: dict[str, Any]) -> int:
    # Postgres JSONB reorders object keys, so skill groups are stored as an ordered list
    value = {**master, "skills": [{"group": g, "items": list(items)} for g, items in master["skills"].items()]}
    stmt = insert(AppState).values(key=STATE_KEY, value=value)
    session.execute(stmt.on_conflict_do_update(index_elements=[AppState.key], set_={"value": value}))
    return sum(len(e.get("bullets") or []) for s in ("experience", "projects") for e in master.get(s) or [])
