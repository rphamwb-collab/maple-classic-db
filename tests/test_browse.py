"""Tests for Phase 3: the item browser filters, browse pages, and the new
item page data (how_to_get, used_in, sellable).

Tests look rows up in the sample database instead of hard-coding lots of IDs,
so they keep working if the sample data grows.
"""

from sqlalchemy import select

from app.models import Item, QuestReward, Recipe, RecipeIngredient
from app.services import browse, filters, queries

HTMX = {"HX-Request": "true"}


def browse_all(db, **params):
    """Run the browser and return every matching item (ignoring pages)."""
    f = filters.clean_filters(params)
    return filters.apply_filters(filters.load_items(db), f)


def option_values(options):
    return [o["value"] for o in options]


# ---------- cleaning URL params ----------

def test_clean_filters_defaults():
    f = filters.clean_filters({})
    assert f == {"class": "all", "type": "", "use": "", "gear": "", "slot": "", "weapon": "", "level": "", "q": "", "page": 1}


def test_gear_groups_and_old_slot_links():
    # Old links with only ?slot=... still work: the gear is worked out from the slot.
    f = filters.clean_filters({"type": "equip", "slot": "hat"})
    assert f["gear"] == "clothes" and f["slot"] == "hat"
    assert filters.clean_filters({"type": "equip", "slot": "shield"})["gear"] == "accessories"
    # Weapons has a single slot, so gear=weapons implies slot=weapon.
    f = filters.clean_filters({"type": "equip", "gear": "weapons"})
    assert f["slot"] == "weapon"
    # A slot from a different group is dropped.
    assert filters.clean_filters({"type": "equip", "gear": "clothes", "slot": "earring"})["slot"] == ""
    # Gear only exists for equips.
    assert filters.clean_filters({"type": "use", "gear": "clothes"})["gear"] == ""


def test_clean_filters_ignores_bad_values():
    f = filters.clean_filters({"class": "pirate", "type": "pets", "level": "abc", "page": "-3"})
    assert f["class"] == "all" and f["type"] == "" and f["level"] == "" and f["page"] == 1


def test_slot_only_with_equip_and_weapon_only_with_weapon_slot():
    assert filters.clean_filters({"type": "use", "slot": "hat"})["slot"] == ""
    assert filters.clean_filters({"type": "equip", "slot": "hat", "weapon": "Bow"})["weapon"] == ""
    f = filters.clean_filters({"type": "equip", "slot": "weapon", "weapon": "Bow"})
    assert f["slot"] == "weapon" and f["weapon"] == "Bow"


def test_weapon_must_fit_the_class():
    # A magician can't filter by Bow; a bowman can.
    assert filters.clean_filters({"class": "magician", "type": "equip", "slot": "weapon",
                                  "weapon": "Bow"})["weapon"] == ""
    assert filters.clean_filters({"class": "bowman", "type": "equip", "slot": "weapon",
                                  "weapon": "Bow"})["weapon"] == "Bow"


def test_level_ranges():
    assert filters.level_ranges(35) == [(0, 10), (11, 20), (21, 30), (31, 40)]
    assert filters.in_level_range(None, "0-10")      # no level counts as 0
    assert not filters.in_level_range(15, "0-10")
    assert filters.in_level_range(15, "11-20")


# ---------- which items match ----------

def test_beginner_means_no_class_requirement(db):
    results = browse_all(db, **{"class": "beginner"})
    assert results
    assert all(item["jobs"] == [] for item in results)


def test_class_tab_shows_items_for_that_class(db):
    results = browse_all(db, **{"class": "warrior"})
    assert results
    assert all("Warrior" in item["jobs"] for item in results)


def test_multi_class_item_shows_under_each_class(db):
    multi = next(i for i in filters.load_items(db) if len(i["jobs"]) >= 2)
    for job in multi["jobs"]:
        ids = [i["id"] for i in browse_all(db, **{"class": job.lower()})]
        assert multi["id"] in ids, job
    # ...but not under beginner
    assert multi["id"] not in [i["id"] for i in browse_all(db, **{"class": "beginner"})]


def test_scrolls_are_a_use_section(db):
    scrolls = browse_all(db, type="use", use="scroll")
    assert scrolls and all(i["sub_type"] == "Scroll" for i in scrolls)
    # Old ?type=scroll links open Use > Scrolls.
    assert filters.clean_filters({"type": "scroll"}) == filters.clean_filters({"type": "use", "use": "scroll"})
    # "use" only exists on the Use type.
    assert filters.clean_filters({"type": "equip", "use": "hp"})["use"] == ""


def test_use_kind_sorts_potions():
    kind = filters.use_kind
    assert kind("use", "Consume", {"heal_hp": 100}, "") == "hp"
    assert kind("use", "Consume", {"heal_mp": 200}, "") == "mp"
    assert kind("use", "Consume", {"heal_hp": 800, "heal_mp": 800}, "") == "hpmp"
    # Elixirs only describe their healing.
    assert kind("use", "Consume", None, "A legendary potion. Restores 35% of your HP and MP, but...") == "hpmp"
    assert kind("use", "Consume", None, "A legendary potion. Restores 50% of your MP, but...") == "mp"
    assert kind("use", "Consume", None, "Increases Attack Power. Attack Power +10 for 10 min.") == "other"
    assert kind("use", "Scroll", {"success_rate": 100}, "") == "scroll"
    assert kind("etc", "Etc", None, "") == ""


def test_use_sections_only_after_picking_use(db):
    items = filters.load_items(db)
    assert filters.use_options(items, filters.clean_filters({})) == []
    options = filters.use_options(items, filters.clean_filters({"type": "use"}))
    assert options[0]["value"] == "" and "scroll" in option_values(options)
    # Every section count adds up to the whole Use type.
    assert sum(o["count"] for o in options[1:]) == options[0]["count"]


def test_slot_and_weapon_filters(db):
    weapons = browse_all(db, type="equip", slot="weapon")
    assert weapons and all(i["equip_slot"] == "Weapon" for i in weapons)
    weapon_type = weapons[0]["weapon_type"]
    narrowed = browse_all(db, type="equip", slot="weapon", weapon=weapon_type)
    assert narrowed and all(i["weapon_type"] == weapon_type for i in narrowed)


def test_class_type_slot_combo(db):
    results = browse_all(db, **{"class": "warrior", "type": "equip", "slot": "weapon"})
    assert results
    for item in results:
        assert "Warrior" in item["jobs"] and item["equip_slot"] == "Weapon"


def test_name_search(db):
    results = browse_all(db, q="potion")
    assert results and all("potion" in i["name"].lower() for i in results)


# ---------- the buttons ----------

def test_options_have_the_agreed_fields(db):
    data = filters.browse_items(db, {"type": "equip"})
    for option in data["class_tabs"] + data["type_options"] + data["slot_options"] + data["level_options"]:
        assert set(option) == {"label", "value", "count", "icon_item_id", "active", "url"}
        assert option["icon_item_id"] is not None or option["count"] == 0


def test_class_tabs_are_always_the_six_tabs(db):
    data = filters.browse_items(db, {"class": "thief"})
    assert option_values(data["class_tabs"]) == ["all", "beginner", "warrior", "magician", "bowman", "thief"]
    assert [t["active"] for t in data["class_tabs"]] == [False, False, False, False, False, True]


def test_zero_count_options_are_hidden(db):
    data = filters.browse_items(db, {"type": "equip"})
    for option in data["type_options"][1:] + data["slot_options"][1:] + data["level_options"][1:]:
        assert option["count"] > 0


def test_slot_and_weapon_options_only_when_relevant(db):
    data = filters.browse_items(db, {"type": "use"})
    assert data["gear_options"] == [] and data["slot_options"] == [] and data["weapon_options"] == []
    data = filters.browse_items(db, {"type": "equip"})
    assert option_values(data["gear_options"])[0] == "" and data["slot_options"] == []
    assert set(option_values(data["gear_options"])[1:]) <= {"weapons", "clothes", "accessories"}
    data = filters.browse_items(db, {"type": "equip", "gear": "weapons"})
    assert data["weapon_options"] and data["slot_options"] == []
    data = filters.browse_items(db, {"type": "equip", "gear": "clothes"})
    offered = option_values(data["slot_options"])[1:]
    assert offered and set(offered) <= set(filters.GEAR_SLOTS["clothes"]) and data["weapon_options"] == []


def test_weapon_options_match_the_class(db):
    data = filters.browse_items(db, {"class": "warrior", "type": "equip", "slot": "weapon"})
    offered = option_values(data["weapon_options"])[1:]  # skip "All weapons"
    assert offered and set(offered) <= set(filters.WEAPONS_BY_CLASS["warrior"])


def test_option_counts_match_clicking_them(db):
    """The number on a button = how many results you get after clicking it."""
    data = filters.browse_items(db, {"type": "equip"})
    assert len(data["gear_options"]) > 1
    for option in data["gear_options"]:
        clicked = filters.browse_items(db, {"type": "equip", "gear": option["value"]})
        assert clicked["total"] == option["count"], option["label"]
    data = filters.browse_items(db, {"type": "equip", "gear": "clothes"})
    for option in data["slot_options"]:
        clicked = filters.browse_items(db, {"type": "equip", "gear": "clothes", "slot": option["value"]})
        assert clicked["total"] == option["count"], option["label"]


def test_option_urls_reset_lower_filters(db):
    data = filters.browse_items(db, {"type": "equip", "slot": "weapon", "level": "0-10"})
    equip = next(o for o in data["type_options"] if o["value"] == "equip")
    assert equip["url"] == "/items?type=equip&level=0-10"  # gear/slot dropped, level kept
    data = filters.browse_items(db, {"class": "warrior", "gear": "weapons"})
    thief = next(o for o in data["class_tabs"] if o["value"] == "thief")
    assert thief["url"] == "/items?class=thief&gear=weapons"  # gear kept; type=equip is implied


def test_class_tabs_are_gear_only(db):
    # Picking a class means equips only: no Type row, and Gear shows straight away.
    data = filters.browse_items(db, {"class": "warrior"})
    assert data["filters"]["type"] == "equip"
    assert data["type_options"] == [] and data["gear_options"]
    assert all(i["category"] == "equip" for i in data["items"])
    # A stray ?type=use on a class tab is ignored.
    assert filters.clean_filters({"class": "thief", "type": "use"})["type"] == "equip"
    # Beginner = equips with no class requirement (not potions, etc items...).
    beginner = filters.browse_items(db, {"class": "beginner"})
    assert all(i["category"] == "equip" and i["jobs"] == [] for i in beginner["items"])
    # From a non-equip view on All, switching to a class drops gear/slot and counts equips.
    data = filters.browse_items(db, {"type": "use"})
    tab = next(o for o in data["class_tabs"] if o["value"] == "warrior")
    assert tab["url"] == "/items?class=warrior"
    assert tab["count"] == filters.browse_items(db, {"class": "warrior"})["total"]


def test_pagination(db):
    data = filters.browse_items(db, {})
    assert data["total"] == len(filters.load_items(db))
    assert len(data["items"]) == min(filters.PAGE_SIZE, data["total"])
    assert data["prev_url"] is None
    assert data["page"] == 1 and data["pages"] >= 1
    # Asking for a page past the end shows the last page.
    assert filters.browse_items(db, {"page": "999"})["page"] == data["pages"]


# ---------- routes ----------

def test_items_page_full_and_htmx_partial(client):
    full = client.get("/items", params={"class": "warrior", "type": "equip"})
    assert full.status_code == 200
    assert full.template.name == "items.html"
    partial = client.get("/items", params={"class": "warrior", "type": "equip"}, headers=HTMX)
    assert partial.status_code == 200
    assert partial.template.name == "partials/item_results.html"
    assert "<html" not in partial.text.lower()
    # The partial gets the same data as the full page.
    assert partial.context["total"] == full.context["total"]


def test_items_page_ignores_junk_params(client):
    assert client.get("/items", params={"class": "x", "type": "y", "page": "z"}).status_code == 200


def test_monsters_page(client):
    r = client.get("/monsters")
    assert r.status_code == 200
    levels = [m["level"] or 0 for m in r.context["monsters"]]
    assert levels == sorted(levels)
    r = client.get("/monsters", params={"level": "0-10"})
    assert r.status_code == 200
    assert all((m["level"] or 0) <= 10 for m in r.context["monsters"])


def test_shops_page(client):
    r = client.get("/shops")
    assert r.status_code == 200
    towns = r.context["towns"]
    assert towns and all(s["item_count"] > 0 for t in towns for s in t["shops"])
    assert r.context["total_shops"] == sum(t["shop_count"] for t in towns)


def test_npcs_redirects_to_shops(client):
    r = client.get("/npcs", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/shops"


def test_home_has_counts_and_tabs(client, db):
    r = client.get("/")
    assert r.status_code == 200
    counts = r.context["counts"]
    assert counts["items"] == len(filters.load_items(db))
    assert counts["shops"] == browse.shops_by_town(db)["total_shops"]
    assert len(r.context["class_tabs"]) == 6


# ---------- item page: how to get it / used in ----------

def test_how_to_get_recipe(db):
    recipe = db.scalar(select(Recipe))
    assert recipe is not None, "sample data should have a recipe"
    data = queries.item_detail(db, recipe.output_item_id)
    recipes = data["how_to_get"]["recipes"]
    assert recipes
    first = recipes[0]
    assert set(first) == {"discipline", "discipline_level", "req_level", "meso_cost",
                          "result_count", "ingredients"}
    assert first["ingredients"] and set(first["ingredients"][0]) == {"item_id", "name", "count"}


def test_how_to_get_quest(db):
    reward = db.scalar(select(QuestReward))
    assert reward is not None, "sample data should have a quest reward"
    quests = queries.item_detail(db, reward.item_id)["how_to_get"]["quests"]
    assert any(q["quest_name"] == reward.quest_name and q["count"] == reward.count for q in quests)


def test_how_to_get_includes_shops_and_drops(db):
    data = queries.item_detail(db, 2000000)  # Red Potion: sold in a shop and dropped by snails
    assert data["how_to_get"]["shops"] == data["shops"] and data["shops"]
    assert data["how_to_get"]["drops"] == data["drops"] and data["drops"]


def test_used_in(db):
    ingredient = db.scalar(select(RecipeIngredient).where(RecipeIngredient.item_id.is_not(None)))
    assert ingredient is not None, "sample data should have a matched ingredient"
    used_in = queries.item_detail(db, ingredient.item_id)["used_in"]
    row = next(u for u in used_in if u["result"]["id"] == ingredient.recipe.output_item_id)
    assert row["count"] == ingredient.count


def test_known_sample_rows(db):
    """Specific sample rows data-engineer added for these tests."""
    # Bronze Bandana is Warrior + Thief: in both tabs, not in Beginner/Magician.
    bandana = 1002043
    for cls, expected in (("warrior", True), ("thief", True), ("beginner", False), ("magician", False)):
        ids = [i["id"] for i in browse_all(db, **{"class": cls, "type": "equip", "slot": "hat"})]
        assert (bandana in ids) == expected, cls
    # Work Gloves recipe has an ingredient that couldn't be matched to an item.
    recipe = queries.item_detail(db, 1082002)["how_to_get"]["recipes"][0]
    unmatched = [i for i in recipe["ingredients"] if i["item_id"] is None]
    assert unmatched and unmatched[0]["name"] == "Processed Leather"
    # Snail Shell is used to craft the Brown Bamboo Hat (x10).
    used_in = queries.item_detail(db, 4000019)["used_in"]
    assert any(u["result"]["id"] == 1002008 and u["count"] == 10 for u in used_in)
    # Warrior weapon filter offers more than one weapon type.
    data = filters.browse_items(db, {"class": "warrior", "type": "equip", "slot": "weapon"})
    assert {"1H Sword", "2H Sword"} <= set(option_values(data["weapon_options"]))


def test_sellable_flag(db):
    # v2.4: no sell price means "unknown" (None), not "can't sell" (False).
    unknown = db.scalar(select(Item).where(Item.npc_sell_price.is_(None)))
    assert unknown is not None, "sample data should have an item with no NPC sell price"
    assert queries.item_detail(db, unknown.id)["sellable"] is None
    sellable = db.scalar(select(Item).where(Item.npc_sell_price.is_not(None)))
    assert queries.item_detail(db, sellable.id)["sellable"] is True


def test_item_page_has_new_fields(client):
    r = client.get("/items/2000000")
    assert r.status_code == 200
    for key in ("how_to_get", "used_in", "sellable"):
        assert key in r.context
    assert {"equip_slot", "weapon_type", "jobs"} <= set(r.context["item"])
