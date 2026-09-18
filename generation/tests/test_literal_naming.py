"""Named subjects keep their names: the staged front-end's candidate prompts + the blueprint cap (2026-09-17)."""
from btsgen.frontend import stage_map


def test_map_compose_and_compose_only_prompts_carry_the_naming_rule():
    for triad in (False, True):
        for sysp in (stage_map._map_compose_system(triad), stage_map._compose_system(triad)):
            assert "Truman Burbank" in sysp and "NEVER replace a named subject" in sysp
            assert '"name": "<= 32 chars"' in sysp and "<= 24 chars" not in sysp


def test_blueprint_keeps_a_32_char_front_end_name():
    import inspect, btsgen.class_forge as cf
    src = inspect.getsource(cf)
    assert '[:32]' in src and '(c.name or bp["name"])[:24]' not in src
