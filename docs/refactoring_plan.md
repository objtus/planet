# コードベース改善計画

**作成日**: 2026-03-29
**対象**: コードレビューで洗い出した技術的負債の整理

---

## 完了済み

| 日付 | 対象 | 内容 |
|---|---|---|
| 2026-03-29 | `collect_all.py` | レジストリ駆動ループ化（72行→53行）。`COLLECTORS` 辞書 + `GROUPS` エイリアス |
| 2026-03-29 | `summarizer/generate.py` | テンプレート読込を5関数→`_load_template(name)` 1関数に統合 |

---

## 高優先度

### 1. SQL f-string インジェクション除去

**対象**: `dashboard/app.py`（複数箇所）

WHERE 句を f-string で組み立ててから `execute()` に渡している。Tailscale 内部のみのため実害は薄いが構造的に危険。

```python
# 現状（危険な形式）
cur.execute(f"SELECT ... WHERE {log_where} ...", params)

# 改善：条件をパラメータ化するか、ホワイトリスト検証を追加
```

---

### 2. 例外のサイレント握りつぶし修正

**対象**: `summarizer/generate.py`（6箇所）、`collectors/rss.py`

`generate.py` の `except Exception:` がログなしで `return 1`。何が失敗したか追跡不能。

```python
# 現状
except Exception:
    return 1

# 改善
except Exception as e:
    print(f"エラー: {e}", file=sys.stderr)
    return 1
```

`rss.py:40-41` の日時パース失敗も `except Exception: pass` で黙殺されており、意図しないタイムスタンプが DB に入るリスクがある。

---

## 中優先度

### 3. `load_config()` の重複定義統一

**対象**: `collectors/base.py`, `dashboard/app.py`, `summarizer/db.py`, `ingest/api.py`, `importers/common.py`（計6ファイル）

同一実装が散在。共通モジュール化を検討。

**注意**: `Path.resolve()` の有無も不統一（`summarizer/db.py` のみ `.resolve()` あり）。統一する際に合わせて修正。

---

### 4. `BaseCollector.commit()` の整理

**対象**: `collectors/base.py:88-89`

メソッドは定義されているが、各コレクターが自前で `self.conn.commit()` を呼んでいる。`base.commit()` を呼ぶよう統一するか、メソッドを削除する。

---

## 低優先度

### 5. `collect_all.py` の importlib 動的ロード

**対象**: `collect_all.py:42`

現在は `(module_path, class_name)` 文字列でインポートしているため IDE の型サポートが弱い。`COLLECTORS` にクラスそのものを登録すれば解決。

```python
# 現状
COLLECTORS = {
    "misskey": ("collectors.misskey", "MisskeyCollector"),
    ...
}

# 改善案（ただし循環インポートに注意）
from collectors.misskey import MisskeyCollector
COLLECTORS = {
    "misskey": MisskeyCollector,
    ...
}
```

---

### 6. `_run_week_hierarchical` の分割

**対象**: `summarizer/generate.py:532-677`（約130行）

日次ループ・キャッシュ判定・マージが1関数に混在。日次処理を切り出すと見通しが良くなる。Phase 6 M3〜以降の改修時に検討。

---

### 7. `BaseCollector` への context manager 対応

**対象**: `collectors/base.py`

`__enter__`/`__exit__` を実装すると `with` 文で使えるようになり、`collect_all.py` の try-finally が簡潔になる。

---

## 対象外（現時点）

- エラーハンドリングの統一フレームワーク → オーバーエンジニアリング
- `dashboard/app.py` のクラス分割 → 動作に問題なし、リスク大
- テキスト前処理ユーティリティの集約 → 各コレクターの仕様が微妙に異なるため慎重に
