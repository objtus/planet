# Scrapbox → Obsidian vault 連携

Planet の DB に取り込んだ Cosense（Scrapbox）日記を、Obsidian のデイリーノート（既定 `20-daily/YYYY-MM-DD.md`）へ反映する。

## 前提

- サーバー上の vault パスを [`config/settings.toml`](../config/settings.toml) の `[obsidian]` で指定する（例: `vault_path`）。
- **Templater は Obsidian 上では実行されない**。未作成ノートは vault 内 `99-templates/dailynote-template.md` の **` ```dataviewjs` 以降**をコピーし、それより前は [`publisher/obsidian_scrapbox.py`](../publisher/obsidian_scrapbox.py) がテンプレに揃えて生成する。
- 反映本文は HTML コメント境界内のみ置換する（`## Scrapbox（Planet・自動）` ～ `<!-- planet-scrapbox-start/end -->`）。
- Bases 用にフロントマターへ **`scrapbox_planet: true`** を付け、ブロック削除時は外す。

## リンク（Cosense → Obsidian）

同期ブロックの先頭に **その日の日付ページ**への Markdown リンク（`[この日の Cosense ページ](https://scrapbox.io/…)`）が入る。

本文は DB の **生ページ `content`** から自分のアイコン区間を再抽出し、次のような記法を **Markdown の外部リンク**に寄せる（実装は [`collectors/scrapbox.py`](../collectors/scrapbox.py) の `convert_scrapbox_line_to_markdown`）。

| Cosense 側の例 | Obsidian 側 |
|----------------|------------|
| `[[ページ名]]` | `[ページ名](https://scrapbox.io/{project}/エンコード済みパス)` |
| `[ページ名]`（単一括弧・プロジェクト内） | 同上（既に `[text](url)` となった箇所には掛けない） |
| `[ラベル https://example.com/path]` | `[ラベル](https://example.com/path)` |
| `[https://example.com]` | `<https://example.com>` |
| `[/相対/パスタイトル]` | 同一プロジェクトの Cosense URL |

単一括弧だけの内部リンクに対応済み。Cosense の **`[ページタイトル]`** はプロジェクト内リンクとして扱う。

## 設定（`settings.toml`）

| セクション | キー | 意味 |
|------------|------|------|
| `[obsidian]` | `vault_path` | vault の絶対パス |
| `[obsidian]` | `daily_dir` | デイリーノート相対ディレクトリ（既定 `20-daily`） |
| `[obsidian]` | `daily_template` | Templater テンプレ相対パス（Dataview 以降のコピー元） |
| `[obsidian]` | `weather_city`, `weather_max_days_back` | 新規ノート用天気（wttr.in） |
| `[scrapbox]` | `lookback_days` | **日次 cron** の収集・同期窓（暦日。例: 30） |
| `[scrapbox]` | `manual_lookback_days` | **ソース管理の「📝」ボタン**で先に回す広域収集と、その後の vault 同期の窓（例: 120） |

## CLI

```bash
# 1 日だけ
./venv/bin/python -m publisher.obsidian_scrapbox --date 2026-04-05

# 今日から N 暦日（N 省略時は [scrapbox].lookback_days）
./venv/bin/python -m publisher.obsidian_scrapbox --recent
./venv/bin/python -m publisher.obsidian_scrapbox --recent --lookback-days 30
```

Scrapbox 収集だけ広い lookback で上書きする場合（手動・cron 以外）:

```bash
SCRAPBOX_LOOKBACK_DAYS=120 ./venv/bin/python -m collectors.scrapbox
```

## ダッシュボード

**ソース管理**の `scrapbox` 行で、**▶** の隣の **📝** が Obsidian 連携。

1. `manual_lookback_days` の日数で Scrapbox を収集（`SCRAPBOX_LOOKBACK_DAYS` 経由）。
2. 続けて **同じ暦日窓**で vault を一括同期。

収集のみ済ませて同期だけ行いたい場合（開発用）: `POST /api/obsidian/scrapbox-sync?skip_collect=1`

処理は最大数分かかる。ブラウザや **前面のリバースプロキシ**にも read timeout がある場合は、必要に応じて（例: nginx の `proxy_read_timeout`）延長する。

## cron（任意）

[`cron/crontab.txt`](../cron/crontab.txt) 参照。Scrapbox 収集の直後に、**同じ `lookback_days`** で `obsidian_scrapbox --recent` を回すと、毎朝「直近 N 暦日」だけ vault と揃う。

## Obsidian Bases（例）

`.base` のフィルターは Obsidian の版に合わせて調整する。例: `path` に `20-daily` を含み、プロパティ `scrapbox_planet` が true。

```yaml
views:
  - type: table
    name: Scrapbox同期デイリー
```

（具体的な `filters` キーは Bases の UI／版ドキュメントに従う。）

## 同期の定義（暦日窓）

**「今日（JST）から数えて N 日前まで」**の各暦日について:

- DB に日記があればノートへ挿入（無ければテンプレ互換で作成）し `scrapbox_planet: true`。
- DB に無く、ノートに Planet ブロックがあれば **ブロックとプロパティを削除**。
- DB に無くノートも無い日は何もしない。
