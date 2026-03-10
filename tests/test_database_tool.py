import sqlite3
from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestSqlQueryTool:
    async def test_sqlite_select(self, tmp_path):
        from astromesh.tools.builtin.database import SqlQueryTool

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.execute("INSERT INTO users VALUES (2, 'Bob')")
        conn.commit()
        conn.close()
        tool = SqlQueryTool(config={"connection_string": f"sqlite:///{db_path}"})
        result = await tool.execute({"query": "SELECT * FROM users"}, _ctx())
        assert result.success is True
        assert len(result.data["rows"]) == 2
        assert result.data["rows"][0]["name"] == "Alice"

    async def test_read_only_blocks_write(self, tmp_path):
        from astromesh.tools.builtin.database import SqlQueryTool

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.commit()
        conn.close()
        tool = SqlQueryTool(config={"connection_string": f"sqlite:///{db_path}", "read_only": True})
        result = await tool.execute({"query": "INSERT INTO users VALUES (1, 'Hacker')"}, _ctx())
        assert result.success is False

    async def test_missing_connection_string(self):
        from astromesh.tools.builtin.database import SqlQueryTool

        tool = SqlQueryTool(config={})
        result = await tool.execute({"query": "SELECT 1"}, _ctx())
        assert result.success is False
