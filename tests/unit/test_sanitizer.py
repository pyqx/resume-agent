"""Tests for reversible PII masking (core/resume/sanitizer.py)."""

from core.resume.sanitizer import PIIMasker, sanitize_text


class TestPIIMasker:
    def test_phone_roundtrip(self):
        masker = PIIMasker()
        masked = masker.mask("联系电话 13812345678,请致电")
        assert "13812345678" not in masked
        assert "[PII_PHONE_1]" in masked
        assert masker.unmask(masked) == "联系电话 13812345678,请致电"

    def test_two_phones_get_distinct_placeholders(self):
        # Historical bug: placeholders were keyed by field name (md5), so two
        # different phones collapsed into one placeholder.
        masker = PIIMasker()
        masked = masker.mask("主号 13812345678 备用 13987654321")
        assert "[PII_PHONE_1]" in masked
        assert "[PII_PHONE_2]" in masked
        restored = masker.unmask(masked)
        assert "13812345678" in restored
        assert "13987654321" in restored

    def test_same_value_same_placeholder(self):
        masker = PIIMasker()
        masked = masker.mask("a@b.com and again a@b.com")
        assert masked.count("[PII_EMAIL_1]") == 2

    def test_email_and_id(self):
        masker = PIIMasker()
        masked = masker.mask("邮箱 user@example.com 身份证 11010519900101001X")
        assert "user@example.com" not in masked
        assert "11010519900101001X" not in masked
        assert masker.masked_count == 2

    def test_unmask_survives_json_roundtrip(self):
        import json
        masker = PIIMasker()
        masked = masker.mask("call 13812345678")
        payload = json.dumps({"text": masked})
        restored = masker.unmask(json.loads(payload)["text"])
        assert "13812345678" in restored


class TestSanitizeText:
    def test_irreversible_masking(self):
        result = sanitize_text("电话 13812345678 邮箱 a@b.com")
        assert "13812345678" not in result
        assert "a@b.com" not in result
        assert "[REDACTED:phone]" in result
        assert "[REDACTED:email]" in result

    def test_plain_text_unchanged(self):
        assert sanitize_text("正常的简历内容") == "正常的简历内容"
