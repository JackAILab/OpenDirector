from uuid import UUID

from scripts.run_live import uuid7


def test_uuid7_is_rfc_version_7_with_rfc_4122_variant():
    value = UUID(uuid7())
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"
