import json
import threading
import time
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import requests


BASE_URL = 'https://api.mcsrranked.com/users/{}/live'
CONFIG_FILE = Path(__file__).with_name('config.json')

UPDATE_INTERVAL = 5.0

EVENT_ORDER = {
    'projectelo.timeline.forfeit': (1, 'Forfeit'),
    'projectelo.timeline.reset': (2, 'Reset'),
    'projectelo.timeline.death': (3, 'Death'),
    'story.enter_the_nether': (4, 'Enter Nether'),
    'nether.find_bastion': (5, 'Enter Bastion'),
    'nether.find_fortress': (6, 'Enter Fortress'),
    'projectelo.timeline.blind_travel': (7, 'Blind Travel'),
    'story.follow_ender_eye': (8, 'Eye Spy'),
    'story.enter_the_end': (9, 'Enter End'),
}

COMPLETION_ORDER = 10


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

CONFIG_FILE = BASE_DIR / 'config.json'
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)


EVENT_FILE = DATA_DIR / 'events.txt'
NAME_WIDTH = 10
EVENT_WIDTH = 14


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f'設定ファイルがありません: {CONFIG_FILE}\n'
            'config.jsonを作成してください。'
        )

    with CONFIG_FILE.open('r', encoding='utf-8') as f:
        config = json.load(f)

    api_key = str(config.get('api_key', '')).strip()
    username = str(config.get('username', '')).strip()

    if not username:
        raise ValueError('config.json の username が空です。')

    interval = config.get('update_interval', UPDATE_INTERVAL)
    try:
        interval = float(interval)
    except (TypeError, ValueError):
        interval = UPDATE_INTERVAL

    interval = max(1.2, interval)

    output_file = config.get('output_file', True)
    output_file_name = str(
        config.get('output_filename', 'events.txt')
    ).strip()

    if not output_file_name:
        output_file_name = 'events.txt'

    try:
        name_width = max(1, int(config.get('name_width', 10)))
    except (TypeError, ValueError):
        name_width = 10

    try:
        event_width = max(1, int(config.get('event_width', 14)))
    except (TypeError, ValueError):
        event_width = 14

    output_mode = str(config.get('output_mode', 'all')).strip().lower()
    if output_mode not in ('event', 'all', 'completion'):
        output_mode = 'all'

    try:
        rank_start = max(1, int(config.get('rank_start', 1)))
    except (TypeError, ValueError):
        rank_start = 1

    try:
        rank_end = max(rank_start, int(config.get('rank_end', 15)))
    except (TypeError, ValueError):
        rank_end = max(rank_start, 15)

    try:
        rank_width = max(2, int(config.get('rank_width', 3)))
    except (TypeError, ValueError):
        rank_width = 3

    return (
        api_key,
        username,
        interval,
        output_file,
        output_file_name,
        name_width,
        event_width,
        output_mode,
        rank_start,
        rank_end,
        rank_width,
    )


def format_time(milliseconds):
    try:
        milliseconds = max(0, int(milliseconds))
    except (TypeError, ValueError):
        return '--:--.---'

    minutes = milliseconds // 60000
    seconds = (milliseconds % 60000) // 1000
    millis = milliseconds % 1000

    return f'{minutes:02d}:{seconds:02d}.{millis:03d}'


def choose_latest_timeline(timelines):
    candidates = []

    for event in timelines or []:
        event_type = event.get('type')

        if event_type not in EVENT_ORDER:
            continue

        try:
            event_time = int(event.get('time', 0))
        except (TypeError, ValueError):
            continue

        order, display_name = EVENT_ORDER[event_type]

        candidates.append(
            (order, event_time, display_name, event_type)
        )

    if not candidates:
        return None

    event_groups = {}

    for candidate in candidates:
        event_type = candidate[3]
        event_groups.setdefault(event_type, []).append(candidate)

    numbered_candidates = []

    for event_type, events in event_groups.items():
        events.sort(key=lambda x: x[1])

        for number, event in enumerate(events, start=1):
            numbered_candidates.append(event + (number,))

    return max(
        numbered_candidates,
        key=lambda x: (x[1], x[0])
    )


def build_player_rows(data):
    '''
    response:
        [
            {
                'uuid': ...,
                'nickname': ...,
                'event': ...,
                'time': ...,
                'raw_time': ...,
                'event_order': ...,
            },
            ...
        ]
    '''
    players = data.get('players') or []
    timelines = data.get('timelines') or []
    completions = data.get('completions') or []

    # uuid -> nickname
    nickname_by_uuid = {}
    for player in players:
        uuid = player.get('uuid')
        nickname = player.get('nickname')

        if uuid:
            nickname_by_uuid[uuid] = nickname or uuid

    timelines_by_uuid = {}
    for event in timelines:
        uuid = event.get('uuid')
        if uuid:
            timelines_by_uuid.setdefault(uuid, []).append(event)

    completions_by_uuid = {}
    for completion in completions:
        uuid = completion.get('uuid')
        if uuid:
            completions_by_uuid.setdefault(uuid, []).append(completion)

    rows = []

    for player in players:
        uuid = player.get('uuid')
        if not uuid:
            continue

        nickname = nickname_by_uuid.get(uuid, uuid)

        player_completions = completions_by_uuid.get(uuid, [])

        if player_completions:
            valid_completions = []
            for completion in player_completions:
                try:
                    completion_time = int(completion.get('time', 0))
                except (TypeError, ValueError):
                    continue

                valid_completions.append(completion_time)

            if valid_completions:
                completion_time = max(valid_completions)

                rows.append({
                    'uuid': uuid,
                    'nickname': nickname,
                    'event': 'Finish',
                    'time': format_time(completion_time),
                    'raw_time': completion_time,
                    'event_order': COMPLETION_ORDER,
                })
                continue

        latest = choose_latest_timeline(timelines_by_uuid.get(uuid, []))

        if latest is None:
            rows.append({
                'uuid': uuid,
                'nickname': nickname,
                'event': 'Waiting',
                'time': '--:--',
                'raw_time': -1,
                'event_order': 3.5,
            })
            continue

        event_order, raw_time, display_name, event_type, event_number = latest

        if event_type in (
            'projectelo.timeline.death',
            'projectelo.timeline.reset',
        ) and event_number >= 2:
            display_name = f'{display_name} #{event_number}'

        rows.append({
            'uuid': uuid,
            'nickname': nickname,
            'event': display_name,
            'time': format_time(raw_time),
            'raw_time': raw_time,
            'event_order': event_order,
        })

    rows.sort(
        key=lambda row: (
            -row["event_order"],
            row["raw_time"],
            row["nickname"].lower(),
        )
    )
    return rows


class LiveMatchApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Priv-Room Event Viewer')
        self.root.geometry('500x500')
        self.root.minsize(500, 200)

        self.api_key = None
        self.username = None
        self.update_interval = UPDATE_INTERVAL

        self.running = True
        self.fetching = False
        self.last_update = None
        self.last_error = None

        self.tree = None
        self.status_var = tk.StringVar(value='Starting...')
        self.room_var = tk.StringVar(value='')
        self.count_var = tk.StringVar(value='0 players')

        self.room_var = tk.StringVar(value='Match Time --:--')

        self.create_widgets()

        try:
            (
                self.api_key,
                self.username,
                self.update_interval,
                self.output_file,
                output_file_name,
                name_width,
                event_width,
                self.output_mode,
                self.rank_start,
                self.rank_end,
                self.rank_width,
            ) = load_config()

            global EVENT_FILE, NAME_WIDTH, EVENT_WIDTH
            EVENT_FILE = DATA_DIR / Path(output_file_name).name
            NAME_WIDTH = name_width
            EVENT_WIDTH = event_width
        except Exception as e:
            self.status_var.set('Configuration error')
            self.root.after(100, lambda: messagebox.showerror(
                'Configuration Error',
                str(e)
            ))
            return

        self.status_var.set(
            f'Updating every {self.update_interval:g}s'
        )

        self.start_fetch()

        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def create_widgets(self):
        top = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top.pack(fill='x')

        ttk.Label(
            top,
            textvariable=self.room_var,
            font=('', 11, 'bold')
        ).pack(side='left')

        ttk.Label(
            top,
            textvariable=self.count_var
        ).pack(side='right')

        frame = ttk.Frame(self.root, padding=(10, 5, 10, 5))
        frame.pack(fill='both', expand=True)

        columns = ('rank', 'nickname', 'event', 'time')

        self.tree = ttk.Treeview(
            frame,
            columns=columns,
            show='headings',
            selectmode='browse'
        )

        self.tree.heading('rank', text='#')
        self.tree.heading('nickname', text='Player')
        self.tree.heading('event', text='Event')
        self.tree.heading('time', text='Time')

        self.tree.column('rank', width=45, minwidth=40, anchor='center', stretch=False)
        self.tree.column('nickname', width=100, minwidth=80, anchor='w')
        self.tree.column('event', width=100, minwidth=80, anchor='w')
        self.tree.column('time', width=75, minwidth=65, anchor='center', stretch=False)

        scrollbar = ttk.Scrollbar(
            frame,
            orient='vertical',
            command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        bottom = ttk.Frame(self.root, padding=(10, 5, 10, 10))
        bottom.pack(fill='x')

        ttk.Label(
            bottom,
            textvariable=self.status_var
        ).pack(side='left')

        ttk.Button(
            bottom,
            text='Update Now',
            command=self.start_fetch
        ).pack(side='right')

    def start_fetch(self):
        if not self.running:
            return

        if self.fetching:
            return

        self.fetching = True
        self.status_var.set('Updating...')

        thread = threading.Thread(
            target=self.fetch_data,
            daemon=True
        )
        thread.start()

    def fetch_data(self):
        try:
            url = BASE_URL.format(self.username)

            headers = {
                "Accept": "application/json",
            }

            if self.api_key:
                headers["Private-Key"] = self.api_key

            response = requests.get(
                url,
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()
            result = response.json()

            if result.get('status') != 'success':
                raise RuntimeError(
                    f'API returned status: {result.get('status')}'
                )

            data = result.get('data')
            if not isinstance(data, dict):
                raise RuntimeError('API response の data が不正です。')

            rows = build_player_rows(data)

            match_time_ms = data.get('time', 0)

            try:
                match_time_ms = max(0, int(match_time_ms))
            except (TypeError, ValueError):
                match_time = '--:--'
            else:
                minutes = match_time_ms // 60000
                seconds = (match_time_ms % 60000) // 1000
                match_time = f'{minutes:02d}:{seconds:02d}'

            if self.output_file:
                export_top_n(
                    rows,
                    data,
                    mode=self.output_mode,
                    rank_start=self.rank_start,
                    rank_end=self.rank_end,
                    rank_width=self.rank_width,
                    output_file=EVENT_FILE,
                )

            self.root.after(
                0,
                lambda: self.apply_rows(rows, match_time)
            )

        except requests.RequestException as e:
          self.root.after(
                0,
                lambda error=e: self.show_error(f'Network error: {error}')
            )
        except (ValueError, json.JSONDecodeError) as e:
            self.root.after(
                0,
                lambda error=e: self.show_error(f'JSON error: {error}')
            )
        except Exception as e:
            self.root.after(
                0,
                lambda error=e: self.show_error(str(error))
            )
        finally:
            self.root.after(0, self.fetch_finished)

    def apply_rows(self, rows, match_time):
        if not self.running:
            return

        first = self.tree.yview()[0] if self.tree.get_children() else 0

        self.tree.delete(*self.tree.get_children())

        for index, row in enumerate(rows, start=1):
            self.tree.insert(
                '',
                'end',
                values=(
                    index,
                    row['nickname'],
                    row['event'],
                    row['time'],
                )
            )

        if rows:
            self.count_var.set(f'{len(rows)} players')
        else:
            self.count_var.set('0 players')

        if self.tree.get_children():
            self.tree.yview_moveto(first)

        self.last_update = time.time()
        self.last_error = None

        self.room_var.set(f'Match Time {match_time}')

        now = time.strftime('%H:%M:%S')
        self.status_var.set(
            f'Last update: {now}  |  Next update: {self.update_interval:g}s'
        )

    def show_error(self, message):
        if not self.running:
            return

        self.last_error = message
        self.status_var.set(f'Error: {message}')

    def fetch_finished(self):
        if not self.running:
            return

        self.fetching = False

        self.root.after(
            int(self.update_interval * 1000),
            self.start_fetch
        )

    def close(self):
        self.running = False
        self.root.destroy()


def format_fixed_width(value, width):
    value = str(value)
    return value[:width].ljust(width)


def export_top_n(
    rows,
    data,
    mode='event',
    rank_start=1,
    rank_end=5,
    rank_width=2,
    output_file='events.txt',
):
    """
    mode:
        'event'      : Completion以外
        'all'        : Completionを含む全イベント
        'completion' : Completionのみ

    rank_start: 出力開始順位（1始まり）
    rank_end:   出力終了順位（両端を含む）
    rank_width: 順位表示の幅（#を含む）
    output_file: 出力先ファイル
    """

    if mode not in ('event', 'all', 'completion'):
        raise ValueError(
            "mode は 'event', 'all', 'completion' のいずれかを指定してください。"
        )

    if rank_start < 1 or rank_end < rank_start:
        raise ValueError('順位の範囲が不正です。')

    if rank_width < 2:
        raise ValueError('rank_width は2以上を指定してください。')

    nickname_by_uuid = {
        player.get('uuid'): player.get(
            'nickname',
            player.get('uuid')
        )
        for player in data.get('players', [])
        if player.get('uuid')
    }

    completions = []

    for completion in data.get('completions', []):
        uuid = completion.get('uuid')

        try:
            completion_time = int(completion.get('time', 0))
        except (TypeError, ValueError):
            continue

        completions.append({
            'uuid': uuid,
            'nickname': nickname_by_uuid.get(
                uuid, uuid or 'Unknown'
            ),
            'event': 'Finish',
            'time': format_time(completion_time),
            'raw_time': completion_time,
            'event_order': COMPLETION_ORDER,
        })

    if mode == 'completion':
        target_rows = completions

    elif mode == 'event':
        target_rows = [
            row for row in rows
            if row['event'] != 'Finish'
        ]

    else:
        target_rows = [
            row for row in rows
            if row['event'] != 'Finish'
        ] + completions

    target_rows.sort(
        key=lambda row: (
            -row['event_order'],
            row['raw_time'],
            row['nickname'].lower(),
        )
    )

    target_rows = target_rows[rank_start - 1:rank_end]

    lines = []

    for i, row in enumerate(target_rows, start=rank_start):
        rank = f'#{i:<{rank_width - 1}}'

        name = format_fixed_width(
            row['nickname'],
            NAME_WIDTH
        )

        event = format_fixed_width(
            row['event'],
            EVENT_WIDTH
        )

        lines.append(
            f'{rank} {name} {event} {row["time"]}'
        )

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    root = tk.Tk()

    try:
        style = ttk.Style()
        if 'vista' in style.theme_names():
            style.theme_use('vista')
    except Exception:
        pass

    LiveMatchApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()