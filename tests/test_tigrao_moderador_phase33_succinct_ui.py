from app.plugins.tigrao_fsm.parsers import (
    parse_admin_title_action,
    parse_invite_create_action,
    parse_invite_edit_action,
    parse_user_text_action,
    parse_antiflood_setting,
)


def test_phase33_line_based_inputs_remain_supported():
    title = parse_admin_title_action("123456\nModerador")
    assert title.user_id == 123456
    assert title.title == "Moderador"

    tag = parse_user_text_action("123456\nvip", max_text_len=16, allow_empty_text=True, label="tag")
    assert tag.user_id == 123456
    assert tag.text == "vip"

    created = parse_invite_create_action("Entrada VIP\n7d\n100\nnão")
    assert created.name == "Entrada VIP"
    assert created.member_limit == 100
    assert created.creates_join_request is False

    edited = parse_invite_edit_action("https://t.me/+abc\nEntrada\n1h\n0\nsim")
    assert edited.invite_link == "https://t.me/+abc"
    assert edited.create is not None
    assert edited.create.creates_join_request is True

    flood = parse_antiflood_setting("on\n5\n10s\n10m")
    assert flood.enabled is True
    assert flood.config["limit"] == 5
