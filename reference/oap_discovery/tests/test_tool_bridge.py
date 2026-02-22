"""Tests for Ollama tool bridge: converter, executor, and API."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from oap_discovery.config import load_credentials
from oap_discovery.tool_converter import (
    _build_parameters,
    _extract_json_fields,
    _split_stdio_description,
    manifest_to_tool,
    manifest_to_tool_name,
)
from oap_discovery.tool_executor import _inject_credentials, execute_tool_call
from oap_discovery.tool_models import ToolRegistryEntry
from oap_discovery.experience_models import InvocationResult
from oap_discovery.models import InvokeSpec


# --- Name conversion ---


class TestManifestToToolName:
    def test_simple_lowercase(self):
        assert manifest_to_tool_name("grep") == "oap_grep"

    def test_spaces_replaced(self):
        assert manifest_to_tool_name("Fingerstring Reminders") == "oap_fingerstring_reminders"

    def test_mixed_case_and_special_chars(self):
        assert manifest_to_tool_name("myNewscast Meeting Processor") == "oap_mynewscast_meeting_processor"

    def test_single_word_capitalized(self):
        assert manifest_to_tool_name("Summarize") == "oap_summarize"

    def test_already_snake_case(self):
        assert manifest_to_tool_name("my_tool") == "oap_my_tool"

    def test_at_command(self):
        assert manifest_to_tool_name("at") == "oap_at"

    def test_jq_command(self):
        assert manifest_to_tool_name("jq") == "oap_jq"


# --- Field extraction ---


class TestExtractJsonFields:
    def test_extracts_quoted_fields(self):
        desc = "JSON object with 'action' (set, list), 'reminder' (text), and 'when' (time)."
        fields = _extract_json_fields(desc)
        assert fields == ["action", "reminder", "when"]

    def test_no_fields(self):
        assert _extract_json_fields("Plain text input") == []

    def test_ignores_non_field_quotes(self):
        # Capitalized or containing spaces don't match
        assert _extract_json_fields("Like 'Hello World' and 'OK'") == []

    def test_underscore_fields(self):
        fields = _extract_json_fields("Requires 'user_id' and 'api_key'")
        assert fields == ["user_id", "api_key"]


# --- Parameter schema generation ---


class TestSplitStdioDescription:
    def test_empty_description(self):
        stdin, args = _split_stdio_description("")
        assert stdin == "Data to provide on standard input"
        assert args == "Command-line flags and arguments"

    def test_stdin_only(self):
        stdin, args = _split_stdio_description("Text to count, provided on standard input.")
        assert stdin == "Text to count, provided on standard input."
        assert args == "Command-line flags and arguments"

    def test_splits_argument_sentences(self):
        desc = "Text to search through, provided on standard input. The first argument is the regular expression pattern."
        stdin, args = _split_stdio_description(desc)
        assert stdin == "Text to search through, provided on standard input."
        assert args == "The first argument is the regular expression pattern."

    def test_args_only(self):
        desc = "Optional format string or date specification as command arguments. No standard input required."
        stdin, args = _split_stdio_description(desc)
        assert stdin == "No standard input required."
        assert args == "Optional format string or date specification as command arguments."


class TestBuildParameters:
    def test_stdio_method(self):
        manifest = {
            "name": "grep",
            "invoke": {"method": "stdio", "url": "grep"},
            "input": {"format": "text/plain", "description": "Text to search through, provided on standard input. The first argument is the regular expression pattern."},
        }
        params = _build_parameters(manifest)
        assert "stdin" in params.properties
        assert "args" in params.properties
        assert params.required == []
        assert params.properties["stdin"].description == "Text to search through, provided on standard input."
        assert params.properties["args"].description == "The first argument is the regular expression pattern."

    def test_text_plain_input(self):
        manifest = {
            "name": "Summarize",
            "invoke": {"method": "POST", "url": "https://example.com/summarize"},
            "input": {"format": "text/plain", "description": "The text to summarize."},
        }
        params = _build_parameters(manifest)
        assert "input" in params.properties
        assert params.required == ["input"]
        assert params.properties["input"].description == "The text to summarize."

    def test_json_with_extractable_fields(self):
        manifest = {
            "name": "Reminders",
            "invoke": {"method": "POST", "url": "https://example.com/reminders"},
            "input": {
                "format": "application/json",
                "description": "JSON object with 'action' (set, list), 'reminder' (text), 'when' (time), and optional 'deliver_via' (webhook, email, sms).",
            },
        }
        params = _build_parameters(manifest)
        assert "action" in params.properties
        assert "reminder" in params.properties
        assert "when" in params.properties
        assert "deliver_via" in params.properties
        assert set(params.required) == {"action", "reminder", "when", "deliver_via"}

    def test_json_without_extractable_fields(self):
        manifest = {
            "name": "processor",
            "invoke": {"method": "POST", "url": "https://example.com/process"},
            "input": {
                "format": "application/json",
                "description": "JSON data on stdin, plus a filter expression",
            },
        }
        params = _build_parameters(manifest)
        assert "data" in params.properties
        assert params.required == ["data"]

    def test_no_input_spec(self):
        manifest = {
            "name": "Minimal",
            "invoke": {"method": "GET", "url": "https://example.com/api"},
        }
        params = _build_parameters(manifest)
        assert "input" in params.properties
        assert params.required == ["input"]

    def test_stdio_without_input_spec(self):
        manifest = {
            "name": "at",
            "invoke": {"method": "stdio", "url": "at"},
        }
        params = _build_parameters(manifest)
        assert "stdin" in params.properties
        assert "args" in params.properties
        assert params.properties["stdin"].description == "Data to provide on standard input"


# --- Full manifest-to-tool conversion ---


class TestManifestToTool:
    def test_grep_manifest(self, grep_manifest):
        entry = manifest_to_tool("grep", grep_manifest)
        assert entry.domain == "grep"
        assert entry.tool.function.name == "oap_grep"
        assert "stdin" in entry.tool.function.parameters.properties
        assert "args" in entry.tool.function.parameters.properties
        assert entry.tool.type == "function"

    def test_mynewscast_manifest(self, mynewscast_manifest):
        entry = manifest_to_tool("mynewscast.org", mynewscast_manifest)
        assert entry.domain == "mynewscast.org"
        assert entry.tool.function.name == "oap_mynewscast_meeting_processor"
        assert "input" in entry.tool.function.parameters.properties

    def test_minimal_manifest(self, minimal_manifest):
        entry = manifest_to_tool("example.com", minimal_manifest)
        assert entry.tool.function.name == "oap_minimal"
        assert "input" in entry.tool.function.parameters.properties

    def test_fingerstring_manifest(self):
        manifest = {
            "oap": "1.0",
            "name": "Fingerstring Reminders",
            "description": "Sets and manages reminders.",
            "input": {
                "format": "application/json",
                "description": "JSON object with 'action' (set, list, cancel), 'reminder' (text), 'when' (time), and optional 'deliver_via' (webhook, email, sms).",
            },
            "invoke": {"method": "POST", "url": "https://fingerstring.com/api"},
        }
        entry = manifest_to_tool("fingerstring.com", manifest)
        assert entry.tool.function.name == "oap_fingerstring_reminders"
        params = entry.tool.function.parameters
        assert "action" in params.properties
        assert "reminder" in params.properties


# --- Tool execution ---


class TestToolExecution:
    @pytest.fixture
    def http_registry(self) -> dict[str, ToolRegistryEntry]:
        manifest = {
            "oap": "1.0",
            "name": "Summarize",
            "description": "Summarize text.",
            "input": {"format": "text/plain", "description": "Text to summarize"},
            "invoke": {"method": "POST", "url": "https://summarize.example.com/api/v1/summarize"},
        }
        entry = manifest_to_tool("summarize.example.com", manifest)
        return {entry.tool.function.name: entry}

    @pytest.fixture
    def stdio_registry(self) -> dict[str, ToolRegistryEntry]:
        manifest = {
            "oap": "1.0",
            "name": "grep",
            "description": "Searches text.",
            "input": {"format": "text/plain", "description": "Text and pattern"},
            "invoke": {"method": "stdio", "url": "grep"},
        }
        entry = manifest_to_tool("grep", manifest)
        return {entry.tool.function.name: entry}

    @pytest.fixture
    def json_registry(self) -> dict[str, ToolRegistryEntry]:
        manifest = {
            "oap": "1.0",
            "name": "Reminders",
            "description": "Manage reminders.",
            "input": {
                "format": "application/json",
                "description": "JSON with 'action' and 'reminder'.",
            },
            "invoke": {"method": "POST", "url": "https://example.com/reminders"},
        }
        entry = manifest_to_tool("example.com", manifest)
        return {entry.tool.function.name: entry}

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        result = await execute_tool_call("oap_nonexistent", {}, {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_http_text_execution(self, http_registry):
        mock_result = InvocationResult(
            status="success", response_body="Summary here", latency_ms=100
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result):
            result = await execute_tool_call(
                "oap_summarize", {"input": "Long text..."}, http_registry
            )
        assert result == "Summary here"

    @pytest.mark.asyncio
    async def test_stdio_execution(self, stdio_registry):
        mock_result = InvocationResult(
            status="success", response_body="matched line", latency_ms=10
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result) as mock_invoke:
            result = await execute_tool_call(
                "oap_grep",
                {"stdin": "hello world\nfoo bar", "args": "hello"},
                stdio_registry,
            )
        assert result == "matched line"
        # Verify args were split into positional params
        call_kwargs = mock_invoke.call_args
        params = call_kwargs[1].get("params") or call_kwargs[0][1]
        assert "arg0" in params
        assert params["arg0"] == "hello"
        # Verify stdin was piped
        assert call_kwargs[1]["stdin_text"] == "hello world\nfoo bar"

    @pytest.mark.asyncio
    async def test_stdio_stdin_only(self, stdio_registry):
        """Stdio tool with stdin but no args (e.g. wc with no flags)."""
        wc_manifest = {
            "oap": "1.0",
            "name": "wc",
            "description": "Count lines, words, and characters.",
            "input": {"format": "text/plain", "description": "Text to count"},
            "invoke": {"method": "stdio", "url": "wc"},
        }
        entry = manifest_to_tool("wc", wc_manifest)
        registry = {entry.tool.function.name: entry}

        mock_result = InvocationResult(
            status="success", response_body="      1       2      12\n", latency_ms=10
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result) as mock_invoke:
            result = await execute_tool_call(
                "oap_wc", {"stdin": "hello world"}, registry
            )
        assert "2" in result
        call_kwargs = mock_invoke.call_args
        assert call_kwargs[1]["stdin_text"] == "hello world"
        # No command-line args
        params = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("params", {})
        assert params == {}

    @pytest.mark.asyncio
    async def test_stdio_args_fallback(self, stdio_registry):
        """When LLM sends wrong key name (e.g. 'keyword' instead of 'args'),
        the executor falls back to the first non-stdin string value."""
        mock_result = InvocationResult(
            status="success", response_body="apropos output", latency_ms=10
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result) as mock_invoke:
            result = await execute_tool_call(
                "oap_grep",
                {"keyword": "image"},  # LLM invented 'keyword' instead of 'args'
                stdio_registry,
            )
        assert result == "apropos output"
        call_kwargs = mock_invoke.call_args
        params = call_kwargs[1].get("params") or call_kwargs[0][1]
        assert "arg0" in params
        assert params["arg0"] == "image"

    @pytest.mark.asyncio
    async def test_json_execution(self, json_registry):
        mock_result = InvocationResult(
            status="success", response_body='{"id": "rem_1"}', latency_ms=50
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result) as mock_invoke:
            result = await execute_tool_call(
                "oap_reminders",
                {"action": "set", "reminder": "test"},
                json_registry,
            )
        assert "rem_1" in result

    @pytest.mark.asyncio
    async def test_execution_failure(self, http_registry):
        mock_result = InvocationResult(
            status="failure", latency_ms=100, error="HTTP 500"
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result):
            result = await execute_tool_call(
                "oap_summarize", {"input": "text"}, http_registry
            )
        assert "Error" in result
        assert "500" in result


# --- Chat proxy (mocked Ollama) ---


class TestChatProxy:
    @pytest.mark.asyncio
    async def test_chat_no_tool_calls(self):
        """When Ollama returns no tool calls, response is passed through."""
        from oap_discovery import tool_api
        from oap_discovery.config import OllamaConfig, ToolBridgeConfig
        from oap_discovery.tool_models import ChatMessage, ChatRequest

        # Setup module state
        mock_engine = AsyncMock()
        mock_engine.discover = AsyncMock()

        # Discovery returns no candidates
        from oap_discovery.models import DiscoverResponse
        mock_engine.discover.return_value = DiscoverResponse(task="test")

        mock_store = MagicMock()
        ollama_cfg = OllamaConfig(base_url="http://localhost:11434")
        bridge_cfg = ToolBridgeConfig(enabled=True)

        # Save and set module state
        orig = (tool_api._engine, tool_api._store, tool_api._ollama_cfg, tool_api._tool_bridge_cfg)
        tool_api._engine = mock_engine
        tool_api._store = mock_store
        tool_api._ollama_cfg = ollama_cfg
        tool_api._tool_bridge_cfg = bridge_cfg

        try:
            ollama_response = {
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "Hello!"},
                "done": True,
            }

            with patch("oap_discovery.tool_api.httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.json.return_value = ollama_response
                mock_resp.raise_for_status = MagicMock()

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_resp
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                req = ChatRequest(
                    model="qwen3:4b",
                    messages=[ChatMessage(role="user", content="hello")],
                )
                result = await tool_api.chat_proxy(req)

            assert result["message"]["content"] == "Hello!"
            assert result["oap_tools_injected"] == 0
        finally:
            tool_api._engine, tool_api._store, tool_api._ollama_cfg, tool_api._tool_bridge_cfg = orig

    @pytest.mark.asyncio
    async def test_chat_error_not_cached(self):
        """When tool execution returns errors, the experience should NOT be cached."""
        from oap_discovery import tool_api
        from oap_discovery.config import ExperienceConfig, OllamaConfig, ToolBridgeConfig
        from oap_discovery.experience_store import ExperienceStore
        from oap_discovery.tool_models import ChatMessage, ChatRequest
        from oap_discovery.models import DiscoverMatch, DiscoverResponse, InvokeSpec

        mock_engine = AsyncMock()
        mock_store = MagicMock()

        match = DiscoverMatch(
            domain="local/mdfind",
            name="mdfind",
            description="Search files by name",
            invoke=InvokeSpec(method="stdio", url="mdfind"),
            score=0.1,
        )
        mock_engine.discover.return_value = DiscoverResponse(
            task="find large files",
            match=match,
            candidates=[match],
        )
        mock_store.get_manifest.return_value = {
            "oap": "1.0",
            "name": "mdfind",
            "description": "Search files by name",
            "input": {"format": "text/plain", "description": "Query"},
            "invoke": {"method": "stdio", "url": "mdfind"},
        }

        ollama_cfg = OllamaConfig(base_url="http://localhost:11434")
        bridge_cfg = ToolBridgeConfig(enabled=True)

        # Wire up a real experience store so we can verify nothing was saved
        import tempfile, os
        tmp_dir = tempfile.mkdtemp()
        exp_store = ExperienceStore(os.path.join(tmp_dir, "test_exp.db"))
        exp_cfg = ExperienceConfig(enabled=True, confidence_threshold=0.85)

        # Mock experience engine to return a fingerprint but no cache hit
        mock_exp_engine = AsyncMock()
        mock_exp_engine.fingerprint_intent.return_value = (
            "search.file.size_filter",
            "file.management",
        )

        orig = (
            tool_api._engine, tool_api._store, tool_api._ollama_cfg,
            tool_api._tool_bridge_cfg, tool_api._experience_engine,
            tool_api._experience_store, tool_api._experience_cfg,
        )
        tool_api._engine = mock_engine
        tool_api._store = mock_store
        tool_api._ollama_cfg = ollama_cfg
        tool_api._tool_bridge_cfg = bridge_cfg
        tool_api._experience_engine = mock_exp_engine
        tool_api._experience_store = exp_store
        tool_api._experience_cfg = exp_cfg

        try:
            # Ollama returns a tool call, then a final answer
            tool_call_resp = {
                "model": "qwen3:4b",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "oap_mdfind",
                                "arguments": {"args": "-size +100M"},
                            }
                        }
                    ],
                },
                "done": True,
            }
            final_resp = {
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "Error occurred."},
                "done": True,
            }

            # Tool execution returns an error
            mock_invocation = InvocationResult(
                status="failure", error="Unknown error", latency_ms=10
            )

            with patch("oap_discovery.tool_api.httpx.AsyncClient") as MockClient, \
                 patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_invocation):

                mock_client_instance = AsyncMock()
                resp1 = MagicMock()
                resp1.json.return_value = tool_call_resp
                resp1.raise_for_status = MagicMock()
                resp2 = MagicMock()
                resp2.json.return_value = final_resp
                resp2.raise_for_status = MagicMock()
                mock_client_instance.post.side_effect = [resp1, resp2]
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                req = ChatRequest(
                    model="qwen3:4b",
                    messages=[ChatMessage(role="user", content="find large files on disk")],
                )
                result = await tool_api.chat_proxy(req)

            # The experience store should be empty — errors must not be cached
            assert exp_store.count() == 0
            assert result["oap_experience_cache"] == "miss"
        finally:
            (
                tool_api._engine, tool_api._store, tool_api._ollama_cfg,
                tool_api._tool_bridge_cfg, tool_api._experience_engine,
                tool_api._experience_store, tool_api._experience_cfg,
            ) = orig
            exp_store.close()

    @pytest.mark.asyncio
    async def test_chat_with_tool_execution(self):
        """When Ollama returns tool calls, they get executed and looped."""
        from oap_discovery import tool_api
        from oap_discovery.config import OllamaConfig, ToolBridgeConfig
        from oap_discovery.tool_models import ChatMessage, ChatRequest
        from oap_discovery.models import DiscoverMatch, DiscoverResponse, InvokeSpec

        mock_engine = AsyncMock()
        mock_store = MagicMock()

        # Discovery returns one match
        match = DiscoverMatch(
            domain="grep",
            name="grep",
            description="Search text",
            invoke=InvokeSpec(method="stdio", url="grep"),
            score=0.1,
        )
        mock_engine.discover.return_value = DiscoverResponse(
            task="search files",
            match=match,
            candidates=[match],
        )
        mock_store.get_manifest.return_value = {
            "oap": "1.0",
            "name": "grep",
            "description": "Search text",
            "input": {"format": "text/plain", "description": "Text and pattern"},
            "invoke": {"method": "stdio", "url": "grep"},
        }

        ollama_cfg = OllamaConfig(base_url="http://localhost:11434")
        bridge_cfg = ToolBridgeConfig(enabled=True)

        orig = (tool_api._engine, tool_api._store, tool_api._ollama_cfg, tool_api._tool_bridge_cfg)
        tool_api._engine = mock_engine
        tool_api._store = mock_store
        tool_api._ollama_cfg = ollama_cfg
        tool_api._tool_bridge_cfg = bridge_cfg

        try:
            # First Ollama call returns tool_calls, second returns final answer
            tool_call_resp = {
                "model": "qwen3:4b",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "oap_grep",
                                "arguments": {"stdin": "file contents here", "args": "TODO"},
                            }
                        }
                    ],
                },
                "done": True,
            }
            final_resp = {
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "Found 3 TODOs."},
                "done": True,
            }

            mock_invocation = InvocationResult(
                status="success", response_body="TODO: fix\nTODO: test\nTODO: deploy", latency_ms=10
            )

            with patch("oap_discovery.tool_api.httpx.AsyncClient") as MockClient, \
                 patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_invocation):

                mock_client_instance = AsyncMock()
                resp1 = MagicMock()
                resp1.json.return_value = tool_call_resp
                resp1.raise_for_status = MagicMock()
                resp2 = MagicMock()
                resp2.json.return_value = final_resp
                resp2.raise_for_status = MagicMock()
                mock_client_instance.post.side_effect = [resp1, resp2]
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                req = ChatRequest(
                    model="qwen3:4b",
                    messages=[ChatMessage(role="user", content="search for TODO in files")],
                )
                result = await tool_api.chat_proxy(req)

            assert result["message"]["content"] == "Found 3 TODOs."
            assert result["oap_tools_injected"] == 1
            assert result["oap_round"] == 2
        finally:
            tool_api._engine, tool_api._store, tool_api._ollama_cfg, tool_api._tool_bridge_cfg = orig


# --- Credential loading ---


class TestLoadCredentials:
    def test_loads_valid_yaml_file(self, tmp_path: Path):
        cred_file = tmp_path / "credentials.yaml"
        cred_file.write_text(
            "example.com:\n"
            "  key: secret123\n"
            "  type: api_key\n"
            "other.io:\n"
            "  key: tok_abc\n"
            "  type: bearer\n"
        )
        result = load_credentials(cred_file)
        assert result == {
            "example.com": {"key": "secret123", "type": "api_key"},
            "other.io": {"key": "tok_abc", "type": "bearer"},
        }

    def test_returns_empty_dict_when_file_does_not_exist(self, tmp_path: Path):
        result = load_credentials(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_handles_empty_yaml_file(self, tmp_path: Path):
        cred_file = tmp_path / "credentials.yaml"
        cred_file.write_text("")
        result = load_credentials(cred_file)
        assert result == {}

    def test_filters_out_non_dict_entries(self, tmp_path: Path):
        cred_file = tmp_path / "credentials.yaml"
        cred_file.write_text(
            "example.com:\n"
            "  key: valid_key\n"
            "bad_string_entry: just-a-string\n"
            "bad_int_entry: 42\n"
            "bad_list_entry:\n"
            "  - item1\n"
            "  - item2\n"
        )
        result = load_credentials(cred_file)
        assert "example.com" in result
        assert "bad_string_entry" not in result
        assert "bad_int_entry" not in result
        assert "bad_list_entry" not in result

    def test_accepts_path_string(self, tmp_path: Path):
        cred_file = tmp_path / "credentials.yaml"
        cred_file.write_text("api.service.com:\n  key: mykey\n")
        result = load_credentials(str(cred_file))
        assert result == {"api.service.com": {"key": "mykey"}}


# --- Credential injection ---


class TestInjectCredentials:
    def _make_spec(self, **kwargs) -> InvokeSpec:
        base = {"method": "POST", "url": "https://example.com/api"}
        base.update(kwargs)
        return InvokeSpec.model_validate(base)

    def test_api_key_injects_header_using_auth_name(self):
        spec = self._make_spec(auth="api_key", auth_name="X-Custom-Token")
        credentials = {"example.com": {"key": "secret123"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result.headers is not None
        assert result.headers["X-Custom-Token"] == "secret123"

    def test_api_key_defaults_to_x_api_key_when_auth_name_is_none(self):
        spec = self._make_spec(auth="api_key", auth_name=None)
        credentials = {"example.com": {"key": "secret123"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result.headers is not None
        assert result.headers["X-API-Key"] == "secret123"

    def test_bearer_injects_authorization_header(self):
        spec = self._make_spec(auth="bearer")
        credentials = {"example.com": {"key": "tok_abc"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result.headers is not None
        assert result.headers["Authorization"] == "Bearer tok_abc"

    def test_no_credentials_for_domain_returns_spec_unchanged(self):
        spec = self._make_spec(auth="api_key", auth_name="X-API-Key")
        credentials = {"other.com": {"key": "irrelevant"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result is spec

    def test_unknown_auth_type_returns_spec_unchanged(self):
        spec = self._make_spec(auth="oauth2")
        credentials = {"example.com": {"key": "tok_abc"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result is spec

    def test_missing_key_in_credentials_returns_spec_unchanged(self):
        spec = self._make_spec(auth="api_key")
        credentials = {"example.com": {"type": "api_key"}}  # no "key" field
        result = _inject_credentials(spec, "example.com", credentials)
        assert result is spec

    def test_existing_headers_are_preserved_and_merged(self):
        spec = self._make_spec(
            auth="api_key",
            auth_name="X-API-Key",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        credentials = {"example.com": {"key": "secret123"}}
        result = _inject_credentials(spec, "example.com", credentials)
        assert result.headers is not None
        assert result.headers["Content-Type"] == "application/json"
        assert result.headers["Accept"] == "application/json"
        assert result.headers["X-API-Key"] == "secret123"

    def test_original_invoke_spec_is_not_mutated(self):
        original_headers = {"Content-Type": "text/plain"}
        spec = self._make_spec(
            auth="bearer",
            headers=dict(original_headers),
        )
        credentials = {"example.com": {"key": "tok_xyz"}}
        result = _inject_credentials(spec, "example.com", credentials)
        # The returned spec is a new object with the injected header
        assert result is not spec
        # The original headers dict is untouched
        assert spec.headers == original_headers
        assert "Authorization" not in (spec.headers or {})


# --- execute_tool_call with credentials ---


class TestToolExecutionWithCredentials:
    @pytest.fixture
    def api_key_registry(self) -> dict[str, ToolRegistryEntry]:
        manifest = {
            "oap": "1.0",
            "name": "Summarize",
            "description": "Summarize text.",
            "input": {"format": "text/plain", "description": "Text to summarize"},
            "invoke": {
                "method": "POST",
                "url": "https://summarize.example.com/api/v1/summarize",
                "auth": "api_key",
                "auth_name": "X-Service-Key",
            },
        }
        entry = manifest_to_tool("summarize.example.com", manifest)
        return {entry.tool.function.name: entry}

    @pytest.mark.asyncio
    async def test_credentials_are_applied_during_http_invocation(self, api_key_registry):
        credentials = {"summarize.example.com": {"key": "supersecret"}}
        mock_result = InvocationResult(
            status="success", response_body="Great summary.", latency_ms=80
        )
        with patch("oap_discovery.tool_executor.invoke_manifest", return_value=mock_result) as mock_invoke:
            result = await execute_tool_call(
                "oap_summarize",
                {"input": "Long article text..."},
                api_key_registry,
                credentials=credentials,
            )

        assert result == "Great summary."
        # Verify the InvokeSpec passed to invoke_manifest carries the injected header
        call_args = mock_invoke.call_args
        used_spec: InvokeSpec = call_args[0][0]
        assert used_spec.headers is not None
        assert used_spec.headers["X-Service-Key"] == "supersecret"
