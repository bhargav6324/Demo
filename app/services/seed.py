"""Synthetic demo dataset. No real users, catalog claims, or copyrighted excerpts."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.database import Database
from app.models import AuditLog, Base, Holding, Loan, Reservation, Resource, ResourceContent, User, UserProfile
from app.security.passwords import hash_password

DEFAULT_AS_OF = datetime(2026, 10, 30, tzinfo=timezone.utc)
DEMO_PASSWORD = "DemoLibrary123!"
SEED_MARKER = "seed-v1"

# Every title and author below is synthetic. These records are local test fixtures.
CATALOG = [
    ("Python Programming Foundations", "programming", "beginner"),
    ("Machine Learning Essentials", "machine learning", "beginner"),
    ("Getting Started with Generative AI", "generative AI", "beginner"),
    ("Relational Database Design Workshop", "databases", "intermediate"),
    ("Practical Data Science Projects", "data science", "intermediate"),
    ("Research Methods for Computing", "research methods", "beginner"),
    ("Secure API Design Patterns", "security", "advanced"),
    ("Cloud Systems Fundamentals", "cloud computing", "beginner"),
    ("Advanced Neural Network Optimization", "deep learning", "advanced"),
    ("Algorithms and Complexity Studies", "algorithms", "advanced"),
    ("Applied Statistics for Engineers", "statistics", "intermediate"),
    ("Accessible Web Interface Research", "web development", "intermediate"),
    ("Data Structures with Python", "programming", "intermediate"),
    ("Computer Networks Laboratory Notes", "networking", "beginner"),
    ("Operating Systems in Practice", "operating systems", "intermediate"),
    ("Foundations of Information Retrieval", "information retrieval", "beginner"),
    ("Retrieval-Augmented Generation Experiments", "RAG", "advanced"),
    ("Natural Language Processing Case Studies", "NLP", "intermediate"),
    ("Responsible AI Evaluation Methods", "AI evaluation", "advanced"),
    ("Knowledge Graph Construction Research", "knowledge graphs", "advanced"),
    ("Introduction to Digital Libraries", "library science", "beginner"),
    ("Metadata Quality and Cataloging", "library science", "intermediate"),
    ("Distributed Systems Failure Analysis", "distributed systems", "advanced"),
    ("Software Testing with Reproducible Fixtures", "software testing", "intermediate"),
    ("Time Series Demand Modeling", "time series", "advanced"),
    ("Linear Algebra for Data Analysis", "mathematics", "beginner"),
    ("Computer Vision for Document Archives", "computer vision", "advanced"),
    ("Privacy-Aware Recommendation Research", "recommendations", "advanced"),
    ("Scientific Writing and Reference Management", "research methods", "beginner"),
    ("Search Relevance Evaluation Handbook", "information retrieval", "intermediate"),
]


def seed_database(database: Database, as_of: datetime = DEFAULT_AS_OF) -> bool:
    """Seed an empty initialized database atomically; a recorded prior seed is a no-op."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Seed anchor must include a timezone")
    as_of = as_of.astimezone(timezone.utc)
    with database.write_session() as session:
        if session.get(AuditLog, SEED_MARKER) is not None:
            return False
        for table in Base.metadata.sorted_tables:
            if session.scalar(select(func.count()).select_from(table)):
                raise ValueError("Refusing to seed a nonempty database without a seed marker; use a fresh database")

        for number, (name, email, role, courses, interests) in enumerate([
            ("Aarav Demo", "student1@library.example", "student", ["CS101", "DS201"], ["Python", "machine learning"]),
            ("Meera Demo", "student2@library.example", "student", ["AI301", "SE202"], ["generative AI", "security"]),
            ("Librarian Demo", "librarian@library.example", "librarian", [], ["library science", "research methods"]),
        ], 1):
            user = User(user_id=f"user-{number:03}", name=name, email=email, role=role,
                        password_hash=hash_password(DEMO_PASSWORD), created_at=as_of)
            user.profile = UserProfile(courses=courses, interests=interests)
            session.add(user)
        session.flush()

        holdings = {}
        kinds = ["book", "journal", "paper", "ebook", "dissertation"]
        for number, (title, topic, level) in enumerate(CATALOG, 1):
            resource_id = f"res-{number:03}"
            kind = kinds[(number - 1) % len(kinds)]
            access = "restricted" if number % 7 == 0 else "authenticated" if number % 3 == 0 else "public"
            resource = Resource(
                resource_id=resource_id, title=title, authors=[f"Demo Author {number:02}"], type=kind,
                description=f"Synthetic demo resource about {topic}; not an actual publication.",
                topics=[topic, "computing"], level=level, access_level=access, updated_at=as_of,
            )
            resource.content = ResourceContent(
                content=f"Synthetic teaching excerpt for {title}. Topic: {topic}. This text was created for backend testing; it is not an excerpt from a real publication.",
                source=f"Local synthetic fixture {resource_id}", updated_at=as_of,
            )
            digital = kind in {"paper", "ebook"}
            total = 1 if number in {2, 9} else 3
            holding = Holding(holding_id=f"hold-{number:03}", branch="Digital Library" if digital else "Central Library",
                              shelf=f"LICENSE-{number:03}" if digital else f"CS-{number:03}",
                              total_copies=total, available_copies=total)
            resource.holdings = [holding]
            if number in {1, 5, 10}:
                resource.holdings.append(Holding(holding_id=f"hold-{number:03}-eng", branch="Engineering Library",
                                                 shelf=f"ENG-{number:03}", total_copies=2, available_copies=2))
            holdings[number] = holding
            session.add(resource)
        session.flush()

        # id, user number, resource number, borrowed offset, due offset, status, fine minor units, renewals
        for number, user, resource, borrowed, due, status, fine, renewals in [
            (1, 1, 1, -7, 7, "active", 0, 0),
            (2, 1, 2, -20, -3, "overdue", 150, 0),
            (3, 2, 9, -15, -1, "overdue", 50, 0),
            (4, 2, 3, -3, 10, "active", 0, 0),
            (5, 1, 4, -12, 2, "returned", 0, 0),
            (6, 2, 5, -9, 5, "active", 0, 1),
        ]:
            session.add(Loan(
                loan_id=f"loan-{number:03}", user_id=f"user-{user:03}", resource_id=f"res-{resource:03}",
                holding_id=holdings[resource].holding_id, borrowed_at=as_of + timedelta(days=borrowed),
                due_at=as_of + timedelta(days=due), returned_at=as_of - timedelta(days=2) if status == "returned" else None,
                status=status, fine_amount_minor=fine, renewal_count=renewals,
            ))
            if status != "returned":
                holdings[resource].available_copies -= 1

        for number, user, resource, status, position in [
            (1, 1, 6, "active", None),
            (2, 2, 2, "waitlisted", 1),
            (3, 3, 2, "waitlisted", 2),
            (4, 2, 7, "active", None),
            (5, 1, 8, "cancelled", None),
            (6, 1, 4, "fulfilled", None),
        ]:
            session.add(Reservation(
                reservation_id=f"reservation-{number:03}", user_id=f"user-{user:03}", resource_id=f"res-{resource:03}",
                status=status, queue_position=position,
                allocated_holding_id=holdings[resource].holding_id if status == "active" else None,
                created_at=as_of - timedelta(hours=12 - number),
            ))
            if status == "active":
                holdings[resource].available_copies -= 1
        session.add(AuditLog(audit_id=SEED_MARKER, user_id=None, action="demo.seed", result="success", trace_id=SEED_MARKER, created_at=as_of))
    return True
