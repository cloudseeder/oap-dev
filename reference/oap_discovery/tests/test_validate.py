"""Tests for manifest validation."""

from oap_discovery.validate import parse_manifest, validate_manifest


class TestValidateManifest:
    def test_valid_full_manifest(self, grep_manifest):
        result = validate_manifest(grep_manifest)
        assert result.valid
        assert not result.errors
        assert not result.warnings

    def test_valid_minimal_manifest(self, minimal_manifest):
        result = validate_manifest(minimal_manifest)
        assert result.valid
        assert not result.errors
        # Should warn about missing input/output
        assert any("input" in w for w in result.warnings)
        assert any("output" in w for w in result.warnings)

    def test_missing_oap(self, grep_manifest):
        del grep_manifest["oap"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("oap" in e for e in result.errors)

    def test_missing_name(self, grep_manifest):
        del grep_manifest["name"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("name" in e for e in result.errors)

    def test_missing_description(self, grep_manifest):
        del grep_manifest["description"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("description" in e for e in result.errors)

    def test_missing_invoke(self, grep_manifest):
        del grep_manifest["invoke"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("invoke" in e for e in result.errors)

    def test_wrong_oap_version(self, grep_manifest):
        grep_manifest["oap"] = "0.1"
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("version" in e for e in result.errors)

    def test_invoke_missing_method(self, grep_manifest):
        del grep_manifest["invoke"]["method"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("invoke.method" in e for e in result.errors)

    def test_invoke_missing_url(self, grep_manifest):
        del grep_manifest["invoke"]["url"]
        result = validate_manifest(grep_manifest)
        assert not result.valid
        assert any("invoke.url" in e for e in result.errors)

    def test_long_description_warning(self, grep_manifest):
        grep_manifest["description"] = "x" * 1500
        result = validate_manifest(grep_manifest)
        assert result.valid  # Warning, not error
        assert any("1500" in w for w in result.warnings)

    def test_empty_dict(self):
        result = validate_manifest({})
        assert not result.valid
        assert len(result.errors) == 4  # All 4 required fields missing


class TestParseManifest:
    def test_parse_valid(self, grep_manifest):
        m = parse_manifest(grep_manifest)
        assert m.oap == "1.0"
        assert m.name == "grep"
        assert m.invoke.method == "stdio"

    def test_parse_minimal(self, minimal_manifest):
        m = parse_manifest(minimal_manifest)
        assert m.input is None
        assert m.output is None

    def test_parse_invalid_raises(self):
        with __import__("pytest").raises(ValueError, match="Invalid manifest"):
            parse_manifest({"name": "bad"})
