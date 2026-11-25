PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS sku;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS stockout_mark;
DROP TABLE IF EXISTS stock_move;
DROP TABLE IF EXISTS decision_log;
DROP TABLE IF EXISTS app_user;

CREATE TABLE sku (
  sku_id          TEXT PRIMARY KEY,
  barcode         TEXT UNIQUE,      -- 贴在包装上的短码，扫码即可定位到单品
  name            TEXT NOT NULL,
  category        TEXT NOT NULL,
  cost            REAL NOT NULL,
  price           REAL NOT NULL,
  salvage         REAL NOT NULL,
  shelf_life_days INTEGER NOT NULL,
  mu              REAL NOT NULL,
  sigma           REAL NOT NULL,
  source          TEXT NOT NULL DEFAULT '自制',  -- 自制 / 进货：决定进订货清单还是备料清单
  spec            TEXT,                         -- 口味、规格等细分描述，可空
  supplier        TEXT                          -- 进货类的供货商，下单时按它分组
);

CREATE TABLE sales (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  sku_id     TEXT NOT NULL REFERENCES sku(sku_id),
  day        TEXT NOT NULL,
  hour       INTEGER NOT NULL,
  weekday    INTEGER NOT NULL,
  qty        INTEGER NOT NULL,
  unit_price REAL NOT NULL
);
CREATE INDEX idx_sales_sku_day ON sales(sku_id, day);

-- 售罄标记：整个项目的灵魂表，字段刻意保持很少
CREATE TABLE stockout_mark (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  sku_id     TEXT NOT NULL REFERENCES sku(sku_id),
  day        TEXT NOT NULL,
  start_hour INTEGER NOT NULL,
  end_hour   INTEGER NOT NULL
);
CREATE INDEX idx_stockout_sku_day ON stockout_mark(sku_id, day);

-- 实物变动流水：入库为正、报损为负、盘点为调整。
-- 库存是派生量，事实是每一次增减；不单独落一张 inventory 表。
CREATE TABLE stock_move (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  sku_id    TEXT NOT NULL REFERENCES sku(sku_id),
  day       TEXT NOT NULL,
  type      TEXT NOT NULL CHECK (type IN ('入库', '报损', '盘点')),
  qty       INTEGER NOT NULL,
  unit_cost REAL,
  status    TEXT NOT NULL DEFAULT '已到货' CHECK (status IN ('在途', '已到货'))
);
CREATE INDEX idx_move_sku_day ON stock_move(sku_id, day);

CREATE TABLE decision_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  username    TEXT REFERENCES app_user(username),
  sku_id      TEXT REFERENCES sku(sku_id),
  params_json TEXT NOT NULL,
  q_star      REAL NOT NULL,
  adopted_qty REAL,
  adopted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE app_user (
  username TEXT PRIMARY KEY,
  pwd_hash TEXT NOT NULL,
  role     TEXT NOT NULL CHECK (role IN ('owner','clerk'))
);

-- 标签打印记录：记下每款最近一次印了多少，第二天打开默认沿用
CREATE TABLE label_print (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  day    TEXT NOT NULL,
  sku_id TEXT NOT NULL REFERENCES sku(sku_id),
  qty    INTEGER NOT NULL
);
