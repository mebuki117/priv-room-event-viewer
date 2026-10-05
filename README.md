## 説明
Rankedのプレイベートルームの、進行状況を可視化するツール。  

## 設定
| 設定 | 説明 | 備考 |
|----|----|----|
| api_key | RankedのPrivate_key | ゲーム内から、「プロファイル」→「設定」→「Generate & Copy API Private Key」で取得 |
| username | MCID | ホスト、または共同ホストである必要がある |
| update_interval | データの取得間隔（秒） | APIのリクエストは10分間に500回の制限があるため、最短でも1.2秒にする必要がある |

## 追跡イベント
以下のイベントを取得する。上から順に優先的に表示する。
- Finish
- Enter End
- Eye Spy
- Blind Travel
- Enter Fortress
- Enter Bastion
- Enter Nether
- Death
- Reset
- Forfeit