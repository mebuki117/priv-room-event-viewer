## 説明
Rankedのプレイベートルームの、進行状況を可視化するツール。  

## 設定
| 設定 | 説明 | 備考 |
|----|----|----|
| api_key | RankedのPrivate_key | ゲーム内から、「プロフィール」→「設定」→「Generate & Copy API Private Key」で取得 |
| username | MCID | ホスト、または共同ホストである必要がある |
| update_interval | データの取得間隔（秒） | APIのリクエストは10分間に500回の制限があるため、最短でも1.2秒にする必要がある |
| output_file | 進行状況の出力 |  |
| output_filename | 出力のファイル名 |  |
| output_mode | 出力のモード |  `event`: Completion以外<br>`all`: Completionを含む全イベント<br>`completion`: Completionのみ |
| rank_start | 開始順位 |  |
| rank_end | 終了順位 |  |
| rank_width | 順位の表示幅 |  |
| name_width | MCIDの表示幅 |  |
| event_width | イベントの表示幅 |  |

## 追跡イベント
以下のイベントを取得する。上から順に優先的に表示する。
- Finish (Completion)
- Enter End
- Eye Spy
- Blind Travel
- Enter Fortress
- Enter Bastion
- Enter Nether
- Death
- Reset
- Forfeit