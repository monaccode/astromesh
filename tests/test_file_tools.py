from astromesh.tools.base import ToolContext


def _ctx(**kwargs):
    return ToolContext(agent_name="test", session_id="s1", **kwargs)


class TestReadFileTool:
    async def test_read_text_file(self, tmp_path):
        from astromesh.tools.builtin.files import ReadFileTool

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        tool = ReadFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": str(f)}, _ctx())
        assert result.success is True
        assert result.data["content"] == "hello world"

    async def test_blocked_path(self):
        from astromesh.tools.builtin.files import ReadFileTool

        tool = ReadFileTool(config={"allowed_paths": ["/tmp/safe"]})
        result = await tool.execute({"path": "/etc/passwd"}, _ctx())
        assert result.success is False

    async def test_file_not_found(self, tmp_path):
        from astromesh.tools.builtin.files import ReadFileTool

        tool = ReadFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": str(tmp_path / "nope.txt")}, _ctx())
        assert result.success is False


class TestWriteFileTool:
    async def test_write_file(self, tmp_path):
        from astromesh.tools.builtin.files import WriteFileTool

        target = str(tmp_path / "output.txt")
        tool = WriteFileTool(config={"allowed_paths": [str(tmp_path)]})
        result = await tool.execute({"path": target, "content": "hello"}, _ctx())
        assert result.success is True
        assert open(target).read() == "hello"

    async def test_blocked_write(self):
        from astromesh.tools.builtin.files import WriteFileTool

        tool = WriteFileTool(config={"allowed_paths": ["/tmp/safe"]})
        result = await tool.execute({"path": "/etc/hacked", "content": "bad"}, _ctx())
        assert result.success is False
