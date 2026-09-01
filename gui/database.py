"""
SQLite database layer for the Rehabilitation Test GUI.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from simulation import generate_historical_session


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "rehab_test.db")


class Database:
    """SQLite database wrapper for client and test session management."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        """Create tables if they do not exist."""
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dob TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS test_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                target_resistance REAL,
                target_angle REAL,
                notes TEXT,
                status TEXT DEFAULT 'completed',
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS test_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp_s REAL NOT NULL,
                rom_angle REAL,
                speed REAL,
                strength REAL,
                spo2 REAL,
                FOREIGN KEY (session_id) REFERENCES test_sessions(id)
            );
        """)
        self.conn.commit()

    # ── Client CRUD ──────────────────────────────────────────────

    def get_clients(self):
        """Return all clients as list of dicts."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clients ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def get_client(self, client_id):
        """Return a single client by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_client(self, name, dob, notes=""):
        """Insert a new client and return their ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO clients (name, dob, notes) VALUES (?, ?, ?)",
            (name, dob, notes),
        )
        self.conn.commit()
        return cursor.lastrowid

    # ── Session CRUD ─────────────────────────────────────────────

    def get_sessions(self, client_id):
        """Return all test sessions for a client."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM test_sessions WHERE client_id = ? ORDER BY date DESC",
            (client_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def create_session(self, client_id, target_resistance, target_angle, notes="", date=None):
        """Create a new test session and return its ID."""
        if date is None:
            date = datetime.now().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO test_sessions (client_id, date, target_resistance, target_angle, notes, status)
               VALUES (?, ?, ?, ?, ?, 'in_progress')""",
            (client_id, date, target_resistance, target_angle, notes),
        )
        self.conn.commit()
        return cursor.lastrowid

    def complete_session(self, session_id):
        """Mark a session as completed."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE test_sessions SET status = 'completed' WHERE id = ?",
            (session_id,),
        )
        self.conn.commit()

    # ── Test Data ────────────────────────────────────────────────

    def save_test_data_batch(self, session_id, timestamps, rom_angles, speeds, strengths, spo2s):
        """Bulk insert test data for a session."""
        cursor = self.conn.cursor()
        data = list(zip(
            [session_id] * len(timestamps),
            timestamps, rom_angles, speeds, strengths, spo2s,
        ))
        cursor.executemany(
            """INSERT INTO test_data (session_id, timestamp_s, rom_angle, speed, strength, spo2)
               VALUES (?, ?, ?, ?, ?, ?)""",
            data,
        )
        self.conn.commit()

    def save_single_sample(self, session_id, timestamp_s, rom_angle, speed, strength, spo2):
        """Insert a single test data sample."""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO test_data (session_id, timestamp_s, rom_angle, speed, strength, spo2)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, timestamp_s, rom_angle, speed, strength, spo2),
        )
        self.conn.commit()

    def get_session_data(self, session_id):
        """Retrieve all test data for a session, ordered by timestamp."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM test_data WHERE session_id = ? ORDER BY timestamp_s",
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ── Dummy Data Seeding ───────────────────────────────────────

    def is_seeded(self):
        """Check if the DB already has dummy data."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clients")
        return cursor.fetchone()[0] > 0

    def seed_dummy_data(self):
        """Populate the database with dummy clients and historical sessions."""
        if self.is_seeded():
            return

        # Create dummy clients
        clients = [
            ("John Martinez", "06-15-1985", "Right bicep tendon repair — isotonic curl rehab, 8 weeks post-op"),
            ("Sarah Chen", "11-03-1992", "Left elbow flexor strain — bicep curl strengthening program"),
            ("Robert Williams", "02-28-1978", "Bilateral bicep curl assessment — post-fracture ROM recovery"),
        ]

        for name, dob, notes in clients:
            client_id = self.create_client(name, dob, notes)

            # 3 historical sessions per client, spread over past weeks
            for i in range(3):
                session_date = (datetime.now() - timedelta(days=(3 - i) * 7)).isoformat()
                data = generate_historical_session(
                    duration=30.0, sample_rate=50, session_index=i
                )

                session_id = self.create_session(
                    client_id=client_id,
                    target_resistance=data["target_resistance"],
                    target_angle=data["target_angle"],
                    notes=f"Historical session {i + 1}",
                    date=session_date,
                )
                # Mark as completed
                self.complete_session(session_id)

                # Insert the data points
                self.save_test_data_batch(
                    session_id,
                    data["timestamps"].tolist(),
                    data["rom_angle"].tolist(),
                    data["speed"].tolist(),
                    data["strength"].tolist(),
                    data["spo2"].tolist(),
                )

    def close(self):
        """Close the database connection."""
        self.conn.close()
