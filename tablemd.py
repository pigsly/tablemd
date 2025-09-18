#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tablemd.py
Windows 下的單機工具：從 Oracle / SQL Server 擷取資料表結構，輸出 Markdown（每表一檔）。
用法（在 CMD）：
  tablemd.bat TXD2BV01
  tablemd.bat ABC%        # LIKE 模式

輸出：
  output/<ID>/TABLE_<TABLE_NAME>.md
  - Oracle: <ID> = ORA_USER
  - SQL Server: <ID> = MSSQL_DBNAME
"""

import os
import sys
from pathlib import Path

# 這兩個依實際需要安裝（Windows 建議先：py -3 -m pip install cx_Oracle pyodbc）
try:
    import cx_Oracle  # Oracle
except Exception:
    cx_Oracle = None

try:
    import pyodbc     # SQL Server
except Exception:
    pyodbc = None


# ----------------------
# 工具函式
# ----------------------
def load_properties(path: Path) -> dict:
    """讀取簡單的 key=value .properties（不支援 section）。"""
    conf = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def md_escape(s: str) -> str:
    """避免 Markdown 表格直條 | 斷欄。"""
    return (s or "").replace("|", "\\|")


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def is_like_pattern(pat: str) -> bool:
    """判斷是否為 LIKE 樣式（含 % 或 _）。"""
    return "%" in pat or "_" in pat


# ----------------------
# Oracle 邏輯
# ----------------------
def oracle_connect(conf: dict):
    # [新增] 支援 SID 與 Service Name 二選一（以 properties 判斷）
    host = conf.get("ORA_HOST")
    port = conf.get("ORA_PORT", "1521")
    user = conf.get("ORA_USER")
    pwd  = conf.get("ORA_PWD")
    sid = conf.get("ORA_SID", "").strip()
    service = conf.get("ORA_SERVICE", "").strip()

    if not cx_Oracle:
        raise RuntimeError("缺少 cx_Oracle，請先安裝：py -3 -m pip install cx_Oracle")

    if service:
        dsn = cx_Oracle.makedsn(host, int(port), service_name=service)
    else:
        # [重點] 使用 SID
        dsn = cx_Oracle.makedsn(host, int(port), sid=sid)

    return cx_Oracle.connect(user, pwd, dsn)


def oracle_fetch_tables(conn, schema: str, table_pat: str):
    """取出符合條件的表名清單（避免在 SQL 內用 :like 綁定變數，繞開 ORA-01745）。"""
    cur = conn.cursor()
    schema_up = schema.upper()

    if is_like_pattern(table_pat):
        # 使用 LIKE 分支
        sql = """
        SELECT table_name
        FROM all_tables
        WHERE owner = :owner
          AND UPPER(table_name) LIKE UPPER(:pat)
        ORDER BY table_name
        """
        cur.execute(sql, dict(owner=schema_up, pat=table_pat))
    else:
        # 使用 = 分支
        sql = """
        SELECT table_name
        FROM all_tables
        WHERE owner = :owner
          AND UPPER(table_name) = UPPER(:pat)
        ORDER BY table_name
        """
        cur.execute(sql, dict(owner=schema_up, pat=table_pat))

    return [r[0] for r in cur.fetchall()]



def oracle_collect_meta(conn, schema: str, table: str):
    cur = conn.cursor()

    schema_up = schema.upper()
    table_up = table.upper()

    cols_sql = """
    SELECT
      c.column_name,
      c.data_type,
      c.data_length,
      c.data_precision,
      c.data_scale,
      c.nullable,
      c.data_default,
      com.comments AS column_comment
    FROM all_tab_columns c
    LEFT JOIN all_col_comments com
      ON com.owner = c.owner AND com.table_name = c.table_name AND com.column_name = c.column_name
    WHERE c.owner = :owner AND c.table_name = :tab
    ORDER BY c.column_id
    """

    pk_sql = """
    SELECT cc.column_name
    FROM all_constraints a
    JOIN all_cons_columns cc
      ON a.owner = cc.owner AND a.constraint_name = cc.constraint_name
    WHERE a.owner = :owner AND a.table_name = :tab AND a.constraint_type = 'P'
    """

    fk_sql = """
    SELECT
      acc.column_name AS col,
      r.table_name    AS r_table,
      rcc.column_name AS r_col
    FROM all_constraints a
    JOIN all_cons_columns acc
      ON a.owner = acc.owner AND a.constraint_name = acc.constraint_name
    JOIN all_constraints r
      ON r.owner = a.r_owner AND r.constraint_name = a.r_constraint_name
    JOIN all_cons_columns rcc
      ON r.owner = rcc.owner AND r.constraint_name = rcc.constraint_name AND rcc.position = acc.position
    WHERE a.owner = :owner AND a.table_name = :tab AND a.constraint_type = 'R'
    """

    # [改] 全部傳大寫
    cur.execute(cols_sql, dict(owner=schema_up, tab=table_up))
    cols = [dict(zip([d[0].lower() for d in cur.description], row)) for row in cur.fetchall()]

    cur.execute(pk_sql, dict(owner=schema_up, tab=table_up))
    pk_cols = {r[0] for r in cur.fetchall()}

    cur.execute(fk_sql, dict(owner=schema_up, tab=table_up))
    fk_map = {}
    for col, rtbl, rcol in cur.fetchall():
        fk_map[col] = f"{rtbl}.{rcol}"

    return cols, pk_cols, fk_map


def oracle_write_md(out_dir: Path, table: str, cols, pk_cols, fk_map, schema_id: str):
    """依指定格式輸出 Markdown（覆蓋）。"""
    lines = []
    lines.append(f"## 表格名稱:{table}\n")
    lines.append("| 欄位 | 資料型別 | 長度/精度 | Nullable | 預設值 | 主鍵 | 外鍵 | 說明 |")
    lines.append("|---|---|---:|:---:|:---:|:---:|:---:|---|")

    for c in cols:
        dtype = c["data_type"]
        # 長度/精度
        lens = ""
        if c["data_precision"] is not None:
            if c["data_scale"] is not None:
                lens = f"{int(c['data_precision'])},{int(c['data_scale'])}"
            else:
                lens = f"{int(c['data_precision'])}"
        elif c["data_length"] is not None:
            lens = str(int(c["data_length"]))

        nullable = "Y" if (c["nullable"] == "Y") else "N"
        default = md_escape((c["data_default"] or "").strip())
        is_pk = "Y" if c["column_name"] in pk_cols else ""
        fk_to = fk_map.get(c["column_name"], "")
        comment = md_escape(c["column_comment"] or "")

        fk_cell = f"FK → `{fk_to}`" if fk_to else ""
        lines.append(f"| {c['column_name']} | {dtype} | {lens} | {nullable} | {default} | {is_pk} | {fk_cell} | {comment} |")

    ensure_dir(out_dir)
    (out_dir / f"TABLE_{table}.md").write_text("\n".join(lines), encoding="utf-8")


# ----------------------
# SQL Server 邏輯
# ----------------------
def mssql_connect(conf: dict):
    if not pyodbc:
        raise RuntimeError("pyodbc not installed. Use: poetry add pyodbc")

    driver = conf.get("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    server = conf.get("MSSQL_SERVER")
    port   = conf.get("MSSQL_PORT", "1433")
    db     = conf.get("MSSQL_DBNAME")
    user   = conf.get("MSSQL_USER")
    pwd    = conf.get("MSSQL_PWD")

    # 新增可控參數（若沒填就給安全/可連的預設）
    encrypt = (conf.get("MSSQL_ENCRYPT", "yes").strip().lower())
    trust   = (conf.get("MSSQL_TRUST_SERVER_CERTIFICATE", "yes").strip().lower())

    # 如果你在域環境用整合驗證，可選：Trusted_Connection=Yes（就不用 UID/PWD）
    trusted_conn = (conf.get("MSSQL_TRUSTED_CONNECTION", "no").strip().lower() in ("1","y","yes","true"))

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server},{port}",
        f"DATABASE={db}",
        f"Encrypt={encrypt}",
        f"TrustServerCertificate={trust}",
    ]
    if trusted_conn:
        parts.append("Trusted_Connection=Yes")
    else:
        parts.append(f"UID={user}")
        parts.append(f"PWD={pwd}")

    dsn = ";".join(parts)
    return pyodbc.connect(dsn)



def mssql_fetch_tables(conn, dbname: str, table_pat: str):
    like = 1 if is_like_pattern(table_pat) else 0
    sql = """
    SELECT t.name
    FROM sys.tables t
    WHERE t.is_ms_shipped = 0
      AND ( (? = 1 AND UPPER(t.name) LIKE UPPER(?))
         OR (? = 0 AND UPPER(t.name) = UPPER(?)) )
    ORDER BY t.name
    """
    cur = conn.cursor()
    cur.execute(sql, (like, table_pat, like, table_pat))
    return [r[0] for r in cur.fetchall()]


def mssql_collect_meta(conn, table: str):
    cur = conn.cursor()

    cols_sql = """
    SELECT
      c.name AS column_name,
      ty.name AS data_type,
      c.max_length,
      c.precision,
      c.scale,
      c.is_nullable,
      dc.definition AS data_default,
      ep.value AS column_comment
    FROM sys.tables t
    JOIN sys.columns c ON t.object_id = c.object_id
    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
    LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
    LEFT JOIN sys.extended_properties ep ON ep.major_id = t.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
    WHERE t.name = ?
    ORDER BY c.column_id
    """

    pk_sql = """
    SELECT c.name
    FROM sys.key_constraints k
    JOIN sys.tables t ON t.object_id = k.parent_object_id
    JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = k.unique_index_id
    JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
    WHERE k.type = 'PK' AND t.name = ?
    """

    # [新增] FK → 參照表.欄位
    fk_sql = """
    SELECT pc.name AS col, rt.name AS r_table, rc.name AS r_col
    FROM sys.foreign_keys f
    JOIN sys.foreign_key_columns fkc ON f.object_id = fkc.constraint_object_id
    JOIN sys.tables pt ON pt.object_id = f.parent_object_id
    JOIN sys.columns pc ON pc.object_id = pt.object_id AND pc.column_id = fkc.parent_column_id
    JOIN sys.tables rt ON rt.object_id = f.referenced_object_id
    JOIN sys.columns rc ON rc.object_id = rt.object_id AND rc.column_id = fkc.referenced_column_id
    WHERE pt.name = ?
    """

    cur.execute(cols_sql, (table,))
    cols = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]

    cur.execute(pk_sql, (table,))
    pk_cols = {r[0] for r in cur.fetchall()}

    cur.execute(fk_sql, (table,))
    fk_map = {}
    for col, rtbl, rcol in cur.fetchall():
        fk_map[col] = f"{rtbl}.{rcol}"

    return cols, pk_cols, fk_map


def mssql_write_md(out_dir: Path, table: str, cols, pk_cols, fk_map, db_id: str):
    lines = []
    lines.append(f"## 表格名稱:{table}\n")
    lines.append("| 欄位 | 資料型別 | 長度/精度 | Nullable | 預設值 | 主鍵 | 外鍵 | 說明 |")
    lines.append("|---|---|---:|:---:|:---:|:---:|:---:|---|")

    for c in cols:
        # 長度/精度
        lens = ""
        prec = c.get("precision")
        scale = c.get("scale")
        maxlen = c.get("max_length")
        if prec and scale is not None and int(prec) != 0:
            lens = f"{int(prec)},{int(scale)}"
        elif maxlen is not None:
            lens = str(int(maxlen))

        nullable = "Y" if c["is_nullable"] else "N"
        default = md_escape((c["data_default"] or "").strip())
        is_pk = "Y" if c["column_name"] in pk_cols else ""
        fk_to = fk_map.get(c["column_name"], "")
        comment = md_escape(c["column_comment"] or "")
        fk_cell = f"FK → `{fk_to}`" if fk_to else ""
        lines.append(f"| {c['column_name']} | {c['data_type']} | {lens} | {nullable} | {default} | {is_pk} | {fk_cell} | {comment} |")

    ensure_dir(out_dir)
    (out_dir / f"TABLE_{table}.md").write_text("\n".join(lines), encoding="utf-8")


# ----------------------
# 主流程
# ----------------------
def main():
    if len(sys.argv) < 2:
        print("用法：tablemd.bat <TABLE_NAME 或 LIKE 樣式（含%%/_）>")
        sys.exit(1)

    table_pat = sys.argv[1]
    prop_path = Path(__file__).with_name("tablemd.properties")
    if not prop_path.exists():
        print(f"找不到設定檔：{prop_path}")
        sys.exit(2)

    conf = load_properties(prop_path)
    db_type = conf.get("DB_TYPE", "").lower()
    output_base = Path(conf.get("OUTPUT_BASE", "output"))

    if db_type == "oracle":
        # [重點] Oracle：用 ORA_USER 作為輸出子目錄名稱
        user_id = conf.get("ORA_USER")
        schema = conf.get("ORA_SCHEMA", user_id)
        out_dir = output_base / (user_id or "ORACLE")
        with oracle_connect(conf) as conn:
            tables = oracle_fetch_tables(conn, schema, table_pat)
            if not tables:
                print(f"[Oracle] 無符合的表（owner={schema}, pattern={table_pat}）")
                return
            for t in tables:
                cols, pk_cols, fk_map = oracle_collect_meta(conn, schema, t)
                oracle_write_md(out_dir, t, cols, pk_cols, fk_map, user_id)
                print(f"[Oracle] 已產出：{out_dir / ('TABLE_' + t + '.md')}")

    elif db_type == "sqlserver":
        # [重點] SQL Server：用 DB 名稱作為輸出子目錄名稱
        db_id = conf.get("MSSQL_DBNAME", "MSSQL")
        out_dir = output_base / db_id
        conn = mssql_connect(conf)
        try:
            tables = mssql_fetch_tables(conn, db_id, table_pat)
            if not tables:
                print(f"[SQL Server] 無符合的表（db={db_id}, pattern={table_pat}）")
                return
            for t in tables:
                cols, pk_cols, fk_map = mssql_collect_meta(conn, t)
                mssql_write_md(out_dir, t, cols, pk_cols, fk_map, db_id)
                print(f"[SQL Server] 已產出：{out_dir / ('TABLE_' + t + '.md')}")
        finally:
            conn.close()

    else:
        print("DB_TYPE 僅支援：oracle 或 sqlserver")
        sys.exit(3)


if __name__ == "__main__":
    main()
