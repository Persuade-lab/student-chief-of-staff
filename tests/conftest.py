import pytest

from src.storage import database


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DATABASE_FILE",
        tmp_path / "student_chief_of_staff.db",
    )
    database.initialize_database()