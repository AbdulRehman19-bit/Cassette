from cassette.cassette import build_cassette
from cassette.differ import diff_cassettes, diff_lines, output_similarity


def tool(name, args, result="r"):
    return {"type": "tool", "server": "github", "name": name, "args": args, "result": {"content": [{"text": result}]}}


def cassette(tools, output="notes", scenario="s"):
    return build_cassette(
        [tool(*t) if isinstance(t, tuple) else t for t in tools], scenario=scenario, input={}, output=output
    )


BASE = [
    ("list_pull_requests", {"state": "closed"}),
    ("get_pull_request_diff", {"number": 412}),
    ("get_pull_request", {"number": 5}),
]


def kinds(d):
    return [e.kind for e in d.entries]


def test_identical_trajectories_pass():
    d = diff_cassettes(cassette(BASE), cassette(BASE))
    assert kinds(d) == ["same"] * 3
    assert d.ok and not d.changed and d.output_same


def test_a_swapped_tool_is_an_args_free_replace_reported_as_remove_plus_add():
    new = [BASE[0], ("get_file_contents", {"path": "CHANGELOG.md"}), BASE[2]]
    d = diff_cassettes(cassette(BASE), cassette(new))
    assert kinds(d) == ["same", "tool_removed", "tool_added", "same"]
    assert not d.ok
    lines = [t for _, t in diff_lines(d)]
    assert lines[0] == "- step 1  get_pull_request_diff(number: 412)"
    assert lines[1] == '+ step 1  get_file_contents(path: "CHANGELOG.md")'


def test_same_tool_with_different_args_is_args_changed():
    new = [BASE[0], ("get_pull_request_diff", {"number": 999}), BASE[2]]
    d = diff_cassettes(cassette(BASE), cassette(new))
    assert kinds(d) == ["same", "tool_args_changed", "same"]
    assert "number: 412 → 999" in "\n".join(t for _, t in diff_lines(d))


def test_added_and_removed_calls():
    d = diff_cassettes(cassette(BASE), cassette([*BASE, ("create_issue", {"title": "x"})]))
    assert kinds(d)[-1] == "tool_added" and not d.ok
    d = diff_cassettes(cassette(BASE), cassette(BASE[:2]))
    assert kinds(d)[-1] == "tool_removed"


def test_ignore_args_and_fail_on_control_what_counts():
    base = [("list_pull_requests", {"state": "closed", "per_page": 30})]
    new = [("list_pull_requests", {"state": "closed", "per_page": 100})]
    assert diff_cassettes(cassette(base), cassette(new), ignore_args=["per_page"]).ok
    assert not diff_cassettes(cassette(base), cassette(new), ignore_args=[], tolerance="exact").ok
    relaxed = diff_cassettes(cassette(BASE), cassette(BASE[:2]), fail_on=["tool_added"])
    assert relaxed.ok and relaxed.changed


def test_result_change_is_reported_but_does_not_fail_by_default():
    d = diff_cassettes(
        cassette([("get_pull_request", {"number": 1}, "old")]), cassette([("get_pull_request", {"number": 1}, "new")])
    )
    assert kinds(d) == ["result_changed"] and d.ok


def test_volatile_values_in_results_do_not_count_as_changes():
    a = cassette([("t", {}, "merged 2026-01-01T00:00:00Z")])
    b = cassette([("t", {}, "merged 2027-05-05T05:05:05Z")])
    assert kinds(diff_cassettes(a, b)) == ["same"]


def test_the_headline_case_looks_fine_but_behavior_changed():
    new = [BASE[0], ("get_file_contents", {"path": "CHANGELOG.md"}), BASE[2]]
    d = diff_cassettes(cassette(BASE, output="## New\n- Dark mode"), cassette(new, output="## New\n- Dark mode!"))
    assert d.behavior_changed_but_output_fine
    assert any("looks fine; behavior changed" in t for _, t in diff_lines(d))


def test_output_similarity_ignores_whitespace_and_scores_differences():
    assert output_similarity("a  b\n", "a b") == 1.0
    assert 0.3 < output_similarity("completely different text", "nothing alike here at all") < 0.8


def test_totals_sum_tokens_and_latency():
    ev = [
        {"type": "model", "request": {}, "response": {}, "usage": {"in": 10, "out": 2}, "ms": 100},
        {**tool("t", {}), "ms": 50},
        {"type": "model", "request": {}, "response": {}, "usage": {"in": 20, "out": 3}, "ms": 100},
    ]
    c = build_cassette(ev, scenario="s", input={}, output="")
    d = diff_cassettes(c, c)
    assert (d.base_totals.tokens_in, d.base_totals.tokens_out) == (30, 5)
    assert d.base_totals.latency_ms == 250 and d.base_totals.model_calls == 2 and d.base_totals.tool_calls == 1


def test_a_divergent_replay_call_shows_up_as_an_added_tool():
    ev = [
        tool("get_pull_request", {"number": 7}),
        {
            "type": "divergence",
            "server": "github",
            "name": "create_issue",
            "args": {"title": "x"},
            "reason": "no answer",
        },
    ]
    new = build_cassette(ev, scenario="s", input={}, output="")
    d = diff_cassettes(cassette([("get_pull_request", {"number": 7})]), new)
    assert kinds(d) == ["same", "tool_added"]
