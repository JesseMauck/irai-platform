"""Research articles (with the free-tier monthly quota), plans, glossary and FAQ."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Article, ArticleView, User
from ..security import limits, optional_user, plans

router = APIRouter(prefix="/api", tags=["content"])
DATA = Path(__file__).resolve().parent.parent / "seed_data"


def _card(a: Article) -> dict:
    return {"slug": a.slug, "title": a.title, "category": a.category, "tickers": a.tickers, "summary": a.summary,
            "author": a.author, "published_at": a.published_at.date().isoformat() if a.published_at else None,
            "read_minutes": a.read_minutes, "premium": a.premium}


@router.get("/research/articles")
def articles(category: str | None = None, db: Session = Depends(get_db)):
    q = select(Article).order_by(Article.published_at.desc())
    if category and category.lower() != "all":
        q = q.where(func.lower(Article.category) == category.lower())
    return [_card(a) for a in db.scalars(q)]


@router.get("/research/articles/{slug}")
def article(slug: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    a = db.scalar(select(Article).where(Article.slug == slug))
    if not a:
        raise HTTPException(404, "Article not found")
    out = _card(a)
    quota = limits(user)["articles_per_month"]
    month = dt.date.today().strftime("%Y-%m")
    locked, reason, remaining = False, None, None
    if quota is not None:
        if user is None:
            locked, reason = a.premium, "Sign in to read premium articles"
        else:
            seen = db.scalar(select(ArticleView).where(ArticleView.user_id == user.id, ArticleView.article_id == a.id,
                                                       ArticleView.month == month))
            used = db.scalar(select(func.count()).select_from(ArticleView).where(
                ArticleView.user_id == user.id, ArticleView.month == month)) or 0
            if not seen:
                if used >= quota:
                    locked, reason = True, f"You've read your {quota} free articles this month"
                else:
                    db.add(ArticleView(user_id=user.id, article_id=a.id, month=month))
                    db.commit()
                    used += 1
            remaining = max(0, quota - used)
    paras = a.body_md.split("\n\n")
    out.update(body_md="\n\n".join(paras[:2]) if locked else a.body_md, locked=locked, lock_reason=reason,
               free_remaining=remaining)
    return out


@router.get("/plans")
def list_plans():
    return list(plans().values())


@router.get("/glossary")
def glossary():
    return json.loads((DATA / "glossary.json").read_text())


@router.get("/faq")
def faq():
    return json.loads((DATA / "faq.json").read_text())


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    """Covered symbols straight from the database (no market calls) — used for the sitemap."""
    from ..models import AdrPair, EtfFund, PeerMember

    return {"adr": sorted(db.scalars(select(AdrPair.adr_symbol)).all()),
            "etf": sorted(db.scalars(select(EtfFund.symbol)).all()),
            "equities": sorted(set(db.scalars(select(PeerMember.symbol)).all())),
            "articles": [{"slug": a.slug, "published_at": a.published_at.date().isoformat() if a.published_at else None}
                         for a in db.scalars(select(Article).order_by(Article.published_at.desc()))]}
