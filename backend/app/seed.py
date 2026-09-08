"""Optional demo material, ingested into a throwaway account.

Not run at startup (every account starts empty). Use it to populate a login for
screenshots / local play:

    python -m app.seed --user demo --password demopass1
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.database import db_session
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.orm import Document, User
from app.services.catalog import ensure_category, seed_default_categories
from app.services.ingestion import ingest_content

logger = get_logger(__name__)

SEED_DOCUMENTS: list[dict] = [
    {
        "title": "Cell Biology — Respiration",
        "category": "Biology",
        "content": """# Respiration

## Aerobic respiration
Aerobic respiration takes place mainly in the mitochondria and requires oxygen.
It fully breaks down glucose to carbon dioxide and water, releasing about 38 ATP
per glucose molecule. The overall word equation is: glucose + oxygen -> carbon
dioxide + water (+ energy).

The three stages are glycolysis (in the cytoplasm), the link reaction and Krebs
cycle (in the mitochondrial matrix), and oxidative phosphorylation at the inner
mitochondrial membrane, where most ATP is made.

## Anaerobic respiration
Anaerobic respiration happens in the cytoplasm and does not use oxygen. It
releases far less energy — only 2 ATP per glucose. In animal cells and bacteria
the product is lactic acid; in yeast and plant cells it is ethanol and carbon
dioxide (fermentation).

Lactic acid build-up in muscle during hard exercise causes fatigue and an oxygen
debt, which is repaid afterwards by continued heavy breathing.
""",
    },
    {
        "title": "Forces and Motion",
        "category": "Physics",
        "content": """# Forces and Motion

## Newton's laws
1. An object stays at rest or moves at constant velocity unless a resultant force
   acts on it (inertia).
2. Resultant force = mass x acceleration (F = ma). Force in newtons, mass in kg,
   acceleration in m/s^2.
3. Every action has an equal and opposite reaction — forces come in pairs acting
   on different objects.

## Equations of motion (constant acceleration)
- v = u + at
- s = ut + 1/2 a t^2
- v^2 = u^2 + 2as

where u is initial velocity, v is final velocity, a is acceleration, t is time
and s is displacement.

## Weight and mass
Mass is the amount of matter (kg) and does not change. Weight is the force of
gravity on that mass: W = mg, where g is about 9.8 N/kg (or 9.8 m/s^2) on Earth.

## Momentum
Momentum p = mv. In a closed system total momentum is conserved in a collision.
Force is also the rate of change of momentum: F = (mv - mu) / t.
""",
    },
    {
        "title": "The French Revolution — Causes",
        "category": "History",
        "content": """# The French Revolution — Causes

## Financial crisis
By the 1780s France was effectively bankrupt. Costly wars — especially support
for the American Revolution — and lavish court spending at Versailles had built
up enormous debt. Around half of state revenue went on servicing that debt.

## An unfair tax system
French society was divided into three Estates. The First Estate (clergy) and
Second Estate (nobility) were largely exempt from the main taxes. The Third
Estate — about 97% of the population, from wealthy merchants to poor peasants —
carried almost the entire tax burden (the taille, the gabelle salt tax, and
feudal dues to landlords).

## Enlightenment ideas
Writers such as Rousseau, Voltaire and Montesquieu spread ideas of popular
sovereignty, natural rights and the separation of powers, undermining the claim
that the king ruled by divine right.

## Immediate triggers
Poor harvests in 1788 pushed bread prices to record highs. The Estates-General
was called in 1789 for the first time since 1614; when the Third Estate was
outvoted by the privileged orders it broke away to form the National Assembly and
swore the Tennis Court Oath. The storming of the Bastille on 14 July 1789 turned
a political crisis into a revolution.
""",
    },
    {
        "title": "Quadratic Equations",
        "category": "Mathematics",
        "content": """# Quadratic Equations

A quadratic equation has the form ax^2 + bx + c = 0, where a is not zero.

## Solving by factorising
Find two numbers that multiply to ac and add to b, split the middle term, then
factor by grouping. Example: x^2 + 5x + 6 = (x + 2)(x + 3) = 0, so x = -2 or
x = -3.

## The quadratic formula
x = ( -b +/- sqrt(b^2 - 4ac) ) / (2a)

This always works. The part under the root, b^2 - 4ac, is the discriminant:
- positive: two distinct real roots
- zero: one repeated real root
- negative: no real roots

## Completing the square
Rewrite ax^2 + bx + c as a(x + b/2a)^2 + (c - b^2/4a). Useful for finding the
turning point of the parabola, which is at x = -b/2a.
""",
    },
]


def ensure_user(db, username: str, password: str) -> User:
    user = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), username=username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    return user


def seed(username: str = "demo", password: str = "demopass1", *, reset: bool = False) -> int:
    with db_session() as db:
        user = ensure_user(db, username, password)
        seed_default_categories(db, user)
        if reset:
            for doc in db.query(Document).filter(Document.user_id == user.id).all():
                db.delete(doc)
            db.flush()
        ingested = 0
        for spec in SEED_DOCUMENTS:
            slug = ensure_category(db, user, spec["category"])
            _, _, deduped = ingest_content(
                db,
                user_id=user.id,
                title=spec["title"],
                content=spec["content"],
                category=slug,
                source_type="text",
                metadata={"seed": True},
            )
            if not deduped:
                ingested += 1
    logger.info("seed_complete", username=username, documents_ingested=ingested)
    return ingested


if __name__ == "__main__":  # python -m app.seed [--user U --password P] [--reset]
    import argparse

    from app.core.database import init_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="demo")
    parser.add_argument("--password", default="demopass1")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    init_db()
    count = seed(args.user, args.password, reset=args.reset)
    print(f"seeded {count} materials into account '{args.user}' (password: {args.password})")
