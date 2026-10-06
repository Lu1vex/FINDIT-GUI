"""SQLite storage for FINDIT (Lost and Found System)."""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_FILE = DATA_DIR / "lost_found.db"
DEFAULT_CATEGORIES = ["Bags", "Electronics", "ID & Cards", "Keys", "Clothing", "Books", "Other"]


class Database:
    """The only class that talks to SQLite. Other modules call its methods."""

    def __init__(self, path=DB_FILE):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        self.con.execute(
            """CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL, name TEXT NOT NULL, category TEXT,
                location TEXT NOT NULL, date TEXT, description TEXT,
                contact TEXT NOT NULL, image TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Open',
                contact_name TEXT DEFAULT '', other_category TEXT DEFAULT '')"""
        )
        self.con.execute(
            """CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL,
                claimed_by TEXT NOT NULL, contact TEXT NOT NULL, proof TEXT,
                released_by TEXT, date TEXT, notes TEXT)"""
        )
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)"
        )

        # Databases made by older versions get the new columns added.
        columns = []
        for row in self.con.execute("PRAGMA table_info(items)"):
            columns.append(row["name"])
        for name in ["contact_name", "other_category"]:
            if name not in columns:
                self.con.execute(f"ALTER TABLE items ADD COLUMN {name} TEXT DEFAULT ''")

        count = self.con.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count == 0:
            for name in DEFAULT_CATEGORIES:
                self.con.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        self.con.commit()

    def add_item(self, kind, name, category, location, date, description, contact, image="",
                 contact_name="", other_category=""):
        """Add a lost or found report and return its id."""
        cursor = self.con.execute(
            "INSERT INTO items (type, name, category, location, date, description, contact, image, "
            "contact_name, other_category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, name, category, location, date, description, contact, image,
             contact_name, other_category),
        )
        self.con.commit()
        return cursor.lastrowid

    def update_item(self, item_id, name, category, location, date, description, contact, image,
                    contact_name="", other_category=""):
        """Change the details of a report. Its type and status stay the same."""
        self.con.execute(
            "UPDATE items SET name=?, category=?, location=?, date=?, description=?, contact=?, "
            "image=?, contact_name=?, other_category=? WHERE id=?",
            (name, category, location, date, description, contact, image,
             contact_name, other_category, item_id),
        )
        self.con.commit()

    def get_items(self, text="", view="All"):
        """Reports that match the text. view is All, Lost, Found (open only) or Claimed."""
        # Escape \ % and _ so they are searched as normal letters, not wildcards.
        text = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + text + "%"

        fields = ["name", "location", "description", "category", "other_category", "contact_name"]
        checks = []
        for field in fields:
            checks.append(f"{field} LIKE ? ESCAPE '\\'")
        sql = "SELECT * FROM items WHERE (" + " OR ".join(checks) + ")"
        values = [pattern] * len(fields)

        if view == "Lost" or view == "Found":
            sql += " AND type=? AND status='Open'"
            values.append(view)
        elif view == "Claimed":
            sql += " AND status='Claimed'"

        sql += " ORDER BY id DESC"
        return self.con.execute(sql, values).fetchall()

    def get_item(self, item_id):
        """One report by id, or None."""
        return self.con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()

    def claim_item(self, item_id, claimed_by, contact, proof="", released_by="", date="", notes=""):
        """Save who claimed a report and mark it Claimed. Both happen together or not at all."""
        with self.con:
            self.con.execute(
                "INSERT INTO claims (item_id, claimed_by, contact, proof, released_by, date, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item_id, claimed_by, contact, proof, released_by, date, notes),
            )
            self.con.execute("UPDATE items SET status='Claimed' WHERE id=?", (item_id,))

    def reopen_item(self, item_id):
        """Mark a claimed report Open again. Old claims are kept as history."""
        self.con.execute("UPDATE items SET status='Open' WHERE id=?", (item_id,))
        self.con.commit()

    def get_claim(self, item_id):
        """The latest claim of a report, or None if it was never claimed."""
        return self.con.execute(
            "SELECT * FROM claims WHERE item_id=? ORDER BY id DESC LIMIT 1", (item_id,)
        ).fetchone()

    def delete_item(self, item_id):
        """Delete a report and its claims."""
        with self.con:
            self.con.execute("DELETE FROM claims WHERE item_id=?", (item_id,))
            self.con.execute("DELETE FROM items WHERE id=?", (item_id,))

    def count(self, where):
        sql = "SELECT COUNT(*) FROM items WHERE " + where
        return self.con.execute(sql).fetchone()[0]

    def totals(self):
        """Counts of (lost, found, claimed) reports."""
        return self.count("type='Lost'"), self.count("type='Found'"), self.count("status='Claimed'")

    def category_names(self):
        names = []
        for row in self.con.execute("SELECT name FROM categories ORDER BY name"):
            names.append(row["name"])
        return names

    def close(self):
        self.con.close()
