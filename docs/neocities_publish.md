# Neocities 公開フロー — 現状まとめ

**最終更新**: 2026-05-15

---

## 公開ルートは2系統ある（別々のもの）

| ルート | 対象ページ | 更新方法 | 自動化状況 |
|--------|-----------|---------|-----------|
| **Planet ページ** | `yuinoid.neocities.org/planet/` | データは自動（cron）、HTML は静的 | **稼働中** |
| **雑記ページ** | `yuinoid.neocities.org/txt/zakki/` | 手動執筆 → 手動アップロード | 自動化を検討中 |

---

## ルート① Planet ページ（稼働済み）

```
【サーバー】
publisher/build_feed.py（cron: 7/15/23時 JST）
    ↓ 過去30日分のJSON生成
~/planet-feed/  →  git push

【Cloudflare Pages】
data.idoko.org/planet-meta.json
data.idoko.org/planet-data.json

【Neocities】
/planet/index.html + planet-app.js
    → fetch(data.idoko.org)  → 描画
```

- Neocities の静的ファイル（`/planet/index.html`、`planet-app.js`、`icons/`）は **手動アップロード**で配置済み
- JSON データは cron で1日3回自動更新 → planet ページは実質的に自動更新されている
- 詳細: `docs/planet_feed_setup.md`、`neocities/planet/README.md`

---

## ルート② 雑記ページ（現在は完全手動）

個人サイト `100percent-health` の雑記セクション。

### ファイル構成

```
txt/zakki/
├── zakki.html              # 雑記トップ
├── txt_main.html           # サイト共通サイドバー（#zakki-list を含む）
├── YYYY/
│   ├── YYYY.html           # 年別インデックス（build_year.py で生成）
│   └── MM/
│       ├── YYYY-MM.html    # 月別インデックス（build_month.py で生成）
│       └── days/
│           └── YYYY-MM-DD.html  # 日別記事（手動執筆）
```

### 現在のワークフロー（手動）

1. Windows の `D:\web\100percent-health\txt\zakki\YYYY\MM\days\` に日別 HTML を執筆
2. `scripts/build_month.py` で月別インデックス（`YYYY-MM.html`）を再生成
3. `scripts/build_year.py` で年別インデックス（`YYYY.html`）を再生成
4. `txt/txt_main.html` の `#zakki-list` に月リンクを手動追記
5. 変更ファイルを Neocities に手動アップロード

### 個人サイトのファイル管理

| 場所 | 役割 |
|------|------|
| `D:\web\100percent-health\` | Windows 編集元（ソース オブ トゥルース） |
| `~/100percent-health\` | サーバー上の同期コピー |
| Neocities | 本番環境 |

**SyncTrayzor（Syncthing）**: 2026-05-15 に設定済み・動作確認済み。  
`~/100percent-health/.stfolder/syncthing-folder-20621d.txt` の存在で確認。  
Windows ↔ サーバー間で双方向リアルタイム同期される。

---

## 今後の検討事項

雑記ページへの AI サマリー自動投稿システム → `docs/zakki_auto_publish.md` を参照
