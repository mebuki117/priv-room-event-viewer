import json
import threading
import time
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

    return api_key, username, interval


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

        self.create_widgets()

        try:
            self.api_key, self.username, self.update_interval = load_config()
        except Exception as e:
            self.status_var.set('Configuration error')
            self.root.after(100, lambda: messagebox.showerror(
                'Configuration Error',
                str(e)
            ))
            return

        self.room_var.set(f'Room Host: {self.username}')
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

            self.root.after(
                0,
                lambda: self.apply_rows(rows)
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

    def apply_rows(self, rows):
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
