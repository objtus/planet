# 雑記自動更新システム — 設計ドキュメント

**最終更新**: 2026-05-15  
**ステータス**: 設計中（未実装）

---

## 目的

Planet の AI サマリー（日次 / 週次 / 月次）を、個人サイト `100percent-health` の雑記ページ
（`yuinoid.neocities.org/txt/zakki/`）に定期的に自動投稿する仕組みを構築する。

雑記ページは従来どおり手動執筆でも更新しつつ、AI サマリー記事を自動で差し込む形を想定する。

---

## 全体フロー（想定）

```
【サーバー】
summarizer/generate.py（既存）
    ↓ AI サマリーを summaries テーブルに保存（日次・週次・月次）

publisher/build_zakki.py（新規）
    ↓ summaries テーブルから取得
    ↓ 雑記 HTML（YYYY-MM-DD.html）を生成
    ↓ ~/100percent-health/txt/zakki/YYYY/MM/days/ に書き出し
    ↓ scripts/build_month.py を呼び出し → YYYY-MM.html 再生成
    ↓ scripts/build_year.py を呼び出し → YYYY.html 再生成
    ↓（任意）txt_main.html の #zakki-list を更新

【SyncTrayzor（Syncthing）】
    ↓ ~/100percent-health/ を Windows の D:\web\100percent-health\ へ自動同期

【Neocities（手動 or 自動）】
    変更ファイルをアップロード
```

---

## 既存の雑記 HTML 構造（参考）

日別記事 `txt/zakki/YYYY/MM/days/YYYY-MM-DD.html` の基本構造:

```html
<article id="YYMMDD" class="daily-article">
  <h3>
    <a href="/txt/zakki/YYYY/MM/days/YYYY-MM-DD.html">
      <time datetime="YYYY-MM-DD">YYYY-MM-DD</time>
    </a>
  </h3>
  <div class="article-body">
    <section>
      <h4 id="セクション名">セクション名 <a href="#セクション名" class="header-link">§</a></h4>
      <p>本文…</p>
    </section>
    <!-- セクションを複数並べる -->
  </div>
</article>
```

外側のページ構造（`<head>`・ヘッダー・パンくず・ナビゲーション等）は
`scripts/build_utils.py` の `generate_html_head()` / `generate_html_footer()` で生成される。

既存ファイルを参考にすることで、新しく生成する記事もサイトのデザインに自然に溶け込む。

---

## 生成する記事の内容

### 日次サマリー記事

- **ファイル**: `txt/zakki/YYYY/MM/days/YYYY-MM-DD.html`
- **タイトル**: `YYYY年MM月DD日の記録`（手動記事とは区別する見出しにしてもよい）
- **本文**: Planet の `summaries` テーブルから当日の各トピック（music / media / health / sns / dev / full）と `oneword` を取得してセクション分け

例（想定）:
```html
<section>
  <h4 id="oneword">ひとこと</h4>
  <p>（oneword サマリーの内容）</p>
</section>
<section>
  <h4 id="summary">日記まとめ</h4>
  <p>（full サマリーの内容）</p>
</section>
<section>
  <h4 id="music">音楽</h4>
  <p>（music サマリーの内容）</p>
</section>
<!-- 以下 media / health / sns / dev -->
```

### 週次・月次（将来）

週次・月次の `summaries` を月別インデックス相当のページに組み込むことも検討できるが、
まず日次から着手する。

---

## 実装に必要なもの

### 新規ファイル

| ファイル | 内容 |
|----------|------|
| `publisher/build_zakki.py` | サマリー→雑記 HTML 変換・書き出しスクリプト |

### 依存するもの（既存）

| ファイル | 役割 |
|----------|------|
| `summarizer/db.py` | DB 接続 |
| `~/100percent-health/scripts/build_month.py` | 月別インデックス再生成 |
| `~/100percent-health/scripts/build_year.py` | 年別インデックス再生成 |
| `~/100percent-health/scripts/build_utils.py` | HTML テンプレート生成 |
| SyncTrayzor | サーバー → Windows への自動同期 |

### 設定（`config/settings.toml` に追加予定）

```toml
[zakki]
# ~/100percent-health のサーバー上パス
site_path = "/home/objtus/100percent-health"
# 自動生成記事に付けるタグ・識別子（任意）
auto_tag = "planet-summary"
# 生成後に build_month / build_year を自動実行するか
run_build_scripts = true
```

---

## 未決事項・検討ポイント

1. **手動記事との共存**: 同じ `days/` ディレクトリに AI 記事を置くか、別ディレクトリ（例: `days/auto/`）にするか。同じにすれば既存の `build_month.py` がそのまま使えるが、区別がつきにくくなる。

2. **既存記事の上書き防止**: 手動で書いた記事と同日に AI 記事を生成しようとした場合の扱い（スキップ / 別ファイル名 / マージ）。

3. **Neocities アップロードの自動化**: SyncTrayzor で Windows に同期したあと、Neocities API（`POST neocities.org/api/upload`）を使ってサーバーから直接アップロードする方法もある（Phase 6 M4）。これが実現すれば完全自動化になる。

4. **txt_main.html の自動更新**: `#zakki-list` に月リンクを追記する処理。新しい月が始まったタイミングで1回だけ追記すれば済むため、条件分岐で実装しやすい。

5. **AI 記事のラベリング**: 生成記事であることを HTML にメタデータや CSS クラスで記録しておくと、将来的な管理がしやすくなる（例: `<article class="daily-article ai-generated">`）。

---

## 関連ドキュメント

| ファイル | 内容 |
|----------|------|
| `docs/neocities_publish.md` | 公開ルート全体の現状まとめ |
| `docs/phase6_plan.md` | Phase 6 M4（Neocities 自動アップロード） |
| `docs/summary_daily_and_dashboard.md` | サマリーパイプライン仕様 |
| `~/100percent-health/scripts/README.md` | build_month / build_year / build_all の使い方 |
