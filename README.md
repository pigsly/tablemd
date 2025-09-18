```markdown
# TableMD

**TableMD** 是一個簡單的 **資料字典產生工具**，可從 **Oracle** 或 **SQL Server** 擷取表格結構，輸出成 Markdown 文件。

輸出格式如下：

```markdown
## 表格名稱:TXD2BV01LOG

| 欄位  | 資料型別 | 長度/精度 | Nullable | 預設值 | 主鍵 | 外鍵             | 說明       |
|-------|----------|-----------|----------|--------|------|------------------|------------|
| COL_A | VARCHAR2 | 50        | N        |        | Y    |                  | 使用者代號 |
| COL_B | NUMBER   | 10,0      | Y        | 0      |      | FK → `OTHER.COL` | 訂單編號   |
```

---

## 功能特點

- 支援 **Oracle (SID 或 ServiceName)** 與 **SQL Server (ODBC Driver 17/18)**。

- 可輸出單一表格或 LIKE 多表格（如 `ABC%`）。

- 每張表格輸出到獨立檔案：
  
  - Oracle → `output/<ORA_USER>/TABLE_<NAME>.md`
  
  - SQL Server → `output/<DBNAME>/TABLE_<NAME>.md`

- 已存在的檔案會直接覆蓋。

- 使用 **Poetry** 管理依賴。

---

## 安裝

1. 安裝 [Poetry](https://python-poetry.org/)（需 Python 3.11+）。

2. 安裝依賴：
   
   ```bash
   poetry install
   ```

3. 確認安裝成功：
   
   ```bash
   poetry run python tablemd.py --help
   ```

---

## 設定檔 (`tablemd.properties`)

在專案根目錄建立 `tablemd.properties`。

### Oracle 範例

```properties
DB_TYPE=oracle
OUTPUT_BASE=output

ORA_HOST=127.0.0.1
ORA_PORT=1521
ORA_SID=ORCL
# ORA_SERVICE=ORCLPDB1
ORA_USER=APPS
ORA_PWD=your_password
ORA_SCHEMA=APPS
```

### SQL Server 範例

```properties
DB_TYPE=sqlserver
OUTPUT_BASE=output

MSSQL_DRIVER=ODBC Driver 18 for SQL Server
MSSQL_SERVER=127.0.0.1
MSSQL_PORT=1433
MSSQL_DBNAME=ERP
MSSQL_USER=sa
MSSQL_PWD=your_password

# 若遇到憑證信任錯誤，請加上
MSSQL_ENCRYPT=yes
MSSQL_TRUST_SERVER_CERTIFICATE=yes
```

---

## 使用方式

### Windows

使用批次檔：

```bat
tablemd.bat TXD2BV01LOG
tablemd.bat ABC%%
```



直接用 Poetry 執行：

```bash
poetry run python tablemd.py TXD2BV01LOG
poetry run python tablemd.py ABC%
```

---

## 執行結果

檔案會輸出到 `output/<ID>/` 目錄下：

```
output/
└── APPS/
    ├── TABLE_TXD2BV01LOG.md
    └── TABLE_ABC123.md
```

---

## 注意事項

- Oracle：
  
  - `ORA_SCHEMA`、`TABLE_NAME` 會自動轉大寫比對。
  
  - 確保已安裝 [Oracle Instant Client](https://www.oracle.com/database/technologies/instant-client/downloads.html) 並加到 `PATH`。

- SQL Server：
  
  - 建議使用 **ODBC Driver 18**。
  
  - 若伺服器憑證非受信任 CA，可設 `MSSQL_TRUST_SERVER_CERTIFICATE=yes`。

- 所有 `.bat`、`.properties` 檔請存成 **UTF-8 (無 BOM)** 或 **ANSI**。

---

## 待辦事項

- 增加 Debug 模式（印出實際 SQL）。

- 增加 `poetry run tablemd` 指令入口。

- 支援 PostgreSQL / MySQL。

---

## readme 資料字典索引 Sample

- ORACLE / `<SCHEMA>`  
  
  - 表清單：
    - [TABLE_TXD2BV01](/schema/uevpecp/TABLE_TXD2BV01.md)

- MSSQL / `<DBNAME>`  
  
  - 表清單：
    - [TABLE_SALES](/docs/schema/MSSQL/<DBNAME>/TABLE_SALES.md)


## 授權

MIT License
