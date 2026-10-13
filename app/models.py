"""Database tables for MapleStory Classic DB.

Each class below is one table. See docs/data-contract.md for the plain-English
description of every field.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Current time in UTC, stored without timezone info (SQLite-friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Parent class that all tables inherit from."""


class Source(Base):
    """Where a record came from (used for credit links and debugging)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    last_scraped: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]]


class Item(Base):
    """An in-game item. `id` is the real game item ID, so it is not auto-numbered."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(20))  # equip / use / etc / setup
    sub_type: Mapped[Optional[str]] = mapped_column(String(50))
    level_req: Mapped[Optional[int]]
    job: Mapped[Optional[str]] = mapped_column(String(30))
    stats: Mapped[Optional[dict]] = mapped_column(JSON)
    description: Mapped[Optional[str]]
    npc_sell_price: Mapped[Optional[int]]
    icon_url: Mapped[Optional[str]] = mapped_column(String(500))
    # v2 fields:
    equip_slot: Mapped[Optional[str]] = mapped_column(String(20), index=True)  # Hat / Top / ... / Weapon
    weapon_type: Mapped[Optional[str]] = mapped_column(String(30))  # e.g. "1H Sword", "Claw"
    jobs: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["Warrior", "Thief"]; [] = any class
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    source: Mapped[Source] = relationship()
    drops: Mapped[list["Drop"]] = relationship(back_populates="item")
    shop_items: Mapped[list["ShopItem"]] = relationship(back_populates="item")
    price_reports: Mapped[list["PriceReport"]] = relationship(back_populates="item")
    drop_reports: Mapped[list["DropReport"]] = relationship(back_populates="item")
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="output_item")  # recipes that craft this
    used_in: Mapped[list["RecipeIngredient"]] = relationship(back_populates="item")  # as an ingredient
    quest_rewards: Mapped[list["QuestReward"]] = relationship(back_populates="item")


class Monster(Base):
    """A monster. `id` is the real game mob ID."""

    __tablename__ = "monsters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    level: Mapped[Optional[int]]
    hp: Mapped[Optional[int]]
    exp: Mapped[Optional[int]]
    maps: Mapped[Optional[list]] = mapped_column(JSON)  # list of map names
    # True for test / unreleased mobs (e.g. Test(Basic), Crimson Balrog): hide from normal lists
    hidden: Mapped[bool] = mapped_column(default=False, index=True)
    # short label shown on the page, e.g. "Invincible obstacle (can't be killed)"; None = no note
    note: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    source: Mapped[Source] = relationship()
    drops: Mapped[list["Drop"]] = relationship(back_populates="monster")
    drop_reports: Mapped[list["DropReport"]] = relationship(back_populates="monster")
    monster_maps: Mapped[list["MonsterMap"]] = relationship(back_populates="monster")  # where it spawns


class Drop(Base):
    """Links a monster to an item it can drop. drop_rate is 0..1, or None if unknown."""

    __tablename__ = "drops"
    __table_args__ = (UniqueConstraint("monster_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monster_id: Mapped[int] = mapped_column(ForeignKey("monsters.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    drop_rate: Mapped[Optional[float]]
    rate_source: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[str] = mapped_column(String(20), default="unverified")
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    monster: Mapped[Monster] = relationship(back_populates="drops")
    item: Mapped[Item] = relationship(back_populates="drops")
    source: Mapped[Source] = relationship()


class Npc(Base):
    """A non-player character, usually a shopkeeper."""

    __tablename__ = "npcs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    town: Mapped[Optional[str]] = mapped_column(String(100))
    map_name: Mapped[Optional[str]] = mapped_column(String(200))
    # short label shown on the page, e.g. "Not open in this release"; None = no note
    note: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    source: Mapped[Source] = relationship()
    shop_items: Mapped[list["ShopItem"]] = relationship(back_populates="npc")
    npc_maps: Mapped[list["NpcMap"]] = relationship(back_populates="npc")  # where it stands


class ShopItem(Base):
    """An item an NPC sells, and what it costs the player (in mesos)."""

    __tablename__ = "shop_items"
    __table_args__ = (UniqueConstraint("npc_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    npc_id: Mapped[int] = mapped_column(ForeignKey("npcs.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    buy_price: Mapped[int]
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    npc: Mapped[Npc] = relationship(back_populates="shop_items")
    item: Mapped[Item] = relationship(back_populates="shop_items")
    source: Mapped[Source] = relationship()


class PriceReport(Base):
    """A market price a player reported. price is mesos PER UNIT."""

    __tablename__ = "price_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    price: Mapped[int]
    quantity: Mapped[int] = mapped_column(default=1)
    world: Mapped[str] = mapped_column(String(50))
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    reporter_ip: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok / flagged

    item: Mapped[Item] = relationship(back_populates="price_reports")


class DropReport(Base):
    """A player's kill log: "I killed N of this monster and saw X of this item"."""

    __tablename__ = "drop_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    monster_id: Mapped[int] = mapped_column(ForeignKey("monsters.id"), index=True)
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), index=True)
    kills: Mapped[int]
    drops_seen: Mapped[int] = mapped_column(default=0)
    world: Mapped[str] = mapped_column(String(50))
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reporter_ip: Mapped[Optional[str]] = mapped_column(String(64))

    monster: Mapped[Monster] = relationship(back_populates="drop_reports")
    item: Mapped[Optional[Item]] = relationship(back_populates="drop_reports")


class Recipe(Base):
    """A crafting recipe. `id` is the OSMS recipe id."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    output_item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    result_count: Mapped[int] = mapped_column(default=1)
    discipline: Mapped[str] = mapped_column(String(30))  # Smithing, Tailoring, ...
    discipline_level: Mapped[int]
    req_level: Mapped[Optional[int]]
    craft_exp: Mapped[Optional[int]]
    meso_cost: Mapped[Optional[int]]
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    output_item: Mapped[Item] = relationship(back_populates="recipes")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
    source: Mapped[Source] = relationship()


class RecipeIngredient(Base):
    """One material a recipe needs. item_id is None if we couldn't match the name."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True)
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(200))
    count: Mapped[int]

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    item: Mapped[Optional[Item]] = relationship(back_populates="used_in")


class QuestReward(Base):
    """An item a quest gives you. One row per (quest, item)."""

    __tablename__ = "quest_rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    quest_id: Mapped[int] = mapped_column(index=True)
    quest_name: Mapped[str] = mapped_column(String(200))
    npc_name: Mapped[Optional[str]] = mapped_column(String(200))
    region: Mapped[Optional[str]] = mapped_column(String(100))
    level_min: Mapped[Optional[int]]
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    count: Mapped[int] = mapped_column(default=1)
    reward_type: Mapped[str] = mapped_column(String(20), default="guaranteed")  # guaranteed / random / choice
    job: Mapped[Optional[str]] = mapped_column(String(20))  # class-specific reward, None = any class
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    item: Mapped[Item] = relationship(back_populates="quest_rewards")
    source: Mapped[Source] = relationship()


class AuditFinding(Base):
    """One disagreement between OSMS and MapleStory Quest, found during `scraper.run`.

    Rebuilt (emptied and refilled) on every run. `check` says what kind:
    - "name_mismatch":     same item ID, different item name
    - "unknown_item_ref":  an MSQ drop/shop row points at an item ID OSMS doesn't have
    - "npc_shop_rejected": an MSQ NPC page is about a different NPC, so we ignored its shop
    """

    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    check: Mapped[str] = mapped_column(String(40), index=True)
    # Plain number, NOT a foreign key: for "unknown_item_ref" the item isn't in our items table.
    item_id: Mapped[Optional[int]] = mapped_column(index=True)
    monster_id: Mapped[Optional[int]] = mapped_column(ForeignKey("monsters.id"), index=True)
    npc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("npcs.id"), index=True)
    detail: Mapped[str]  # plain-English sentence, ready to show on the page
    source_a: Mapped[str] = mapped_column(String(100), default="OSMS Data Explorer")
    source_b: Mapped[str] = mapped_column(String(100), default="MapleStory Quest")
    found_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Map(Base):
    """A Classic game map (e.g. Henesys). `id` is the Classic map ID (differs from v83 IDs).

    world + spot_x/spot_y say where the map sits on the world map picture, in pixels from
    the picture's top-left corner. spot_exact=False means the map has no spot of its own,
    so we use the spot of the town it returns to (return_map_id).
    """

    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), index=True)
    street_name: Mapped[Optional[str]] = mapped_column(String(200))
    region: Mapped[Optional[str]] = mapped_column(String(100))  # OSMS region, e.g. "Victoria Island"
    map_mark: Mapped[Optional[str]] = mapped_column(String(50))  # e.g. "Henesys", "Dungeon"
    is_town: Mapped[bool] = mapped_column(default=False)
    return_map_id: Mapped[Optional[int]]  # plain number, NOT a foreign key
    world: Mapped[Optional[str]] = mapped_column(String(30), index=True)  # maple-island / victoria-island / None
    spot_x: Mapped[Optional[int]]
    spot_y: Mapped[Optional[int]]
    spot_exact: Mapped[Optional[bool]]  # True = own spot, False = town's spot, None = no spot
    v83_map_id: Mapped[Optional[int]]  # matching v83 map (debugging only)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))

    source: Mapped[Source] = relationship()
    monster_maps: Mapped[list["MonsterMap"]] = relationship(back_populates="map")
    npc_maps: Mapped[list["NpcMap"]] = relationship(back_populates="map")


class MonsterMap(Base):
    """A monster spawns on a map. spawn_count = how many spawn there (None if unknown)."""

    __tablename__ = "monster_maps"
    __table_args__ = (UniqueConstraint("monster_id", "map_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    monster_id: Mapped[int] = mapped_column(ForeignKey("monsters.id"), index=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"), index=True)
    spawn_count: Mapped[Optional[int]]

    monster: Mapped[Monster] = relationship(back_populates="monster_maps")
    map: Mapped[Map] = relationship(back_populates="monster_maps")


class NpcMap(Base):
    """An NPC stands on a map."""

    __tablename__ = "npc_maps"
    __table_args__ = (UniqueConstraint("npc_id", "map_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    npc_id: Mapped[int] = mapped_column(ForeignKey("npcs.id"), index=True)
    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id"), index=True)

    npc: Mapped[Npc] = relationship(back_populates="npc_maps")
    map: Mapped[Map] = relationship(back_populates="npc_maps")
