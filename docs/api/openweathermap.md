# OpenWeatherMap API 仕様メモ

## 基本情報

- 無料プラン: 1000コール/日、60コール/分
- 使用するAPI: One Call API 3.0 または Current Weather API（無料）

## 使用するエンドポイント

### 現在の天気を取得（1日1回）

```
GET https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=ja
```

**パラメータ**
| パラメータ | 値 |
|---|---|
| lat | 緯度（名古屋: 35.1815）|
| lon | 経度（名古屋: 136.9066）|
| units | `metric`（摂氏）|
| lang | `ja`（日本語の天気説明）|

**レスポンスから使うフィールド**
```json
{
  "main": {
    "temp": 18.5,
    "temp_min": 12.3,
    "temp_max": 22.1,
    "humidity": 65
  },
  "weather": [
    {"main": "Clear", "description": "快晴"}
  ]
}
```

## APIキーの取得

https://openweathermap.org/api → サインアップ → API Keys

## 注意事項

- 1日1回の取得なので無料枠で十分
- `temp_avg` はAPIでは返ってこない。`(temp_max + temp_min) / 2` で算出する
