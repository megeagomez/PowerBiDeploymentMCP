from powerbi_mcp_server.metadata.drift import check_drift, hash_definition


def test_hash_definition_is_order_independent():
    def_a = {"parts": [{"path": "a.json", "payload": "AAA"}, {"path": "b.json", "payload": "BBB"}]}
    def_b = {"parts": [{"path": "b.json", "payload": "BBB"}, {"path": "a.json", "payload": "AAA"}]}
    assert hash_definition(def_a) == hash_definition(def_b)


def test_hash_definition_changes_with_content():
    def_a = {"parts": [{"path": "a.json", "payload": "AAA"}]}
    def_b = {"parts": [{"path": "a.json", "payload": "ZZZ"}]}
    assert hash_definition(def_a) != hash_definition(def_b)


def test_hash_definition_handles_empty():
    assert hash_definition({}) == hash_definition({"parts": []})


def test_no_drift_when_no_prior_state():
    result = check_drift(state=None, expected_source_profile_id=1, target_live_hash="anything")
    assert result.has_drift is False
    assert result.reasons == []


def test_drift_when_last_operation_was_deploy():
    state = {"last_operation": "deploy", "source_profile_id": None, "definition_hash": "h1"}
    result = check_drift(state, expected_source_profile_id=2, target_live_hash="h1")
    assert result.has_drift is True
    assert any("deploy" in r for r in result.reasons)


def test_drift_when_promoted_from_different_source():
    state = {"last_operation": "promote", "source_profile_id": 99, "definition_hash": "h1"}
    result = check_drift(state, expected_source_profile_id=2, target_live_hash="h1")
    assert result.has_drift is True


def test_drift_when_live_hash_diverges():
    state = {"last_operation": "promote", "source_profile_id": 2, "definition_hash": "h1"}
    result = check_drift(state, expected_source_profile_id=2, target_live_hash="h2-different")
    assert result.has_drift is True


def test_no_drift_when_everything_matches():
    state = {"last_operation": "promote", "source_profile_id": 2, "definition_hash": "h1"}
    result = check_drift(state, expected_source_profile_id=2, target_live_hash="h1")
    assert result.has_drift is False
    assert result.reasons == []
