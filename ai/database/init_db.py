from ai.database.database import engine
from ai.database.models import Base


Base.metadata.create_all(
    bind=engine
)

print(
    "Database initialized successfully."
)