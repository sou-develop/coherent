"""
予備実験プログラム — コヒーレント運動なし・桁数変動

実験フロー（1試行）:
1. 「Enterキーで開始」画面
2. 注視点（1秒）
3. RSVP で数字を1桁ずつ提示（桁数は試行ごとに config で設定）
4. 空白画面で待機（config の preliminary.wait_duration_sec 秒間）
5. 数字入力画面（config の preliminary.input_slots マス）
6. 結果を記録（画面フィードバックなし）

試行構成:
- config の preliminary.digit_lengths_min 〜 digit_lengths_max 桁
- config の preliminary.num_blocks ブロック繰り返し

使い方:
  python3 preliminary_experiment.py
"""

import pygame
import random
import sys
import os
import csv
import json
from datetime import datetime

# ============================================================
# 設定ファイル読み込み
# ============================================================

def _load_json(filename):
    """指定されたJSONファイルを読み込む"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_config = _load_json("config.json")

# ============================================================
# 設定パラメータ（config.json から読み込み）
# ============================================================

# --- 画面設定 ---
_display = _config.get("display", {})
SCREEN_WIDTH = _display.get("screen_width", 1920)
SCREEN_HEIGHT = _display.get("screen_height", 1080)
FULLSCREEN = _display.get("fullscreen", False)
FPS = _display.get("fps", 60)

# --- 予備実験専用設定（config.json の preliminary セクション） ---
_prelim = _config.get("preliminary", {})
DIGIT_DISPLAY_TIME_MS = _prelim.get("digit_display_time_ms", 500)
DIGIT_BLANK_TIME_MS = _prelim.get("digit_blank_time_ms", 100)
WAIT_DURATION_SEC = _prelim.get("wait_duration_sec", 8.0)
DIGIT_LENGTHS_MIN = _prelim.get("digit_lengths_min", 5)
DIGIT_LENGTHS_MAX = _prelim.get("digit_lengths_max", 9)
INPUT_SLOTS = _prelim.get("input_slots", 10)
NUM_BLOCKS = _prelim.get("num_blocks", 3)

# --- RSVP表示設定（フォントサイズ・色は本実験と共有） ---
_rsvp = _config.get("rsvp", {})
DIGIT_FONT_SIZE = _rsvp.get("digit_font_size", 120)
DIGIT_LUMINANCE_RGB = tuple(_rsvp.get("digit_luminance_rgb", [165, 165, 165]))

# --- 入力画面設定 ---
_input_cfg = _config.get("input", {})
INPUT_FONT_SIZE = _input_cfg.get("font_size", 48)
INPUT_COLOR = tuple(_input_cfg.get("color", [255, 255, 255]))
CURSOR_BLINK_MS = _input_cfg.get("cursor_blink_ms", 500)

# --- 予備実験固有の計算値 ---
DIGIT_LENGTHS = list(range(DIGIT_LENGTHS_MIN, DIGIT_LENGTHS_MAX + 1))
TOTAL_TRIALS = len(DIGIT_LENGTHS) * NUM_BLOCKS

SCREEN_BG_COLOR = (0, 0, 0)


# ============================================================
# ユーティリティ
# ============================================================

def generate_digit_sequence(length):
    """ランダムな数字列を生成する"""
    return [random.randint(0, 9) for _ in range(length)]


def generate_trial_list():
    """全試行の条件リストを生成する。

    3ブロック × 9条件（7〜15桁）= 27試行。
    各ブロック内で桁数の順序をランダムにシャッフルする。
    """
    trials = []
    for block in range(NUM_BLOCKS):
        block_lengths = DIGIT_LENGTHS[:]
        random.shuffle(block_lengths)
        for num_digits in block_lengths:
            trials.append({
                "block": block + 1,
                "num_digits": num_digits,
            })
    return trials


# ============================================================
# 予備実験メインクラス
# ============================================================

class PreliminaryExperiment:
    """予備実験のメインクラス（コヒーレント運動なし）"""

    def __init__(self):
        pygame.init()
        if FULLSCREEN:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.width, self.height = self.screen.get_size()
        else:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.width = SCREEN_WIDTH
            self.height = SCREEN_HEIGHT

        pygame.display.set_caption("予備実験 — 数字記憶課題")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # フォントの初期化（クロスプラットフォーム対応）
        FONT_FILE_CANDIDATES = [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "C:/Windows/Fonts/yugothic.ttf",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        ]

        font_path = None
        for path in FONT_FILE_CANDIDATES:
            if os.path.exists(path):
                font_path = path
                break

        def get_font(size):
            if font_path:
                try:
                    return pygame.font.Font(font_path, size)
                except Exception:
                    pass
            return pygame.font.Font(None, size)

        self.digit_font = get_font(DIGIT_FONT_SIZE)
        self.fixation_font = get_font(36)
        self.input_font = get_font(INPUT_FONT_SIZE)
        self.label_font = get_font(32)
        self.small_font = get_font(24)
        self.title_font = get_font(56)

        # 実験データ
        self.digit_sequence = []
        self.user_responses = []
        self.all_results = []
        self.response_time_ms = 0
        subject_info = _load_json("subject.json")
        self.subject_no = str(subject_info.get("subject_no", "001"))
        self.trial_list = []
        self.current_trial_idx = 0

    # --------------------------------------------------------
    # ヘルパー
    # --------------------------------------------------------
    def handle_quit_events(self):
        """終了イベントを処理"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                return event
        return None

    def draw_text_centered(self, text, font, color, y_offset=0):
        """テキストを画面中央に描画"""
        surface = font.render(text, True, color)
        rect = surface.get_rect(center=(self.width // 2, self.height // 2 + y_offset))
        self.screen.blit(surface, rect)

    # --------------------------------------------------------
    # 開始画面
    # --------------------------------------------------------
    def phase_start_screen(self):
        """開始画面（Enterキーで開始）"""
        self.screen.fill(SCREEN_BG_COLOR)
        self.draw_text_centered("Enterキーで開始", self.label_font,
                                (255, 255, 255), 0)
        pygame.display.flip()

        while True:
            event = self.handle_quit_events()
            if event and event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                break
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # フェーズ 1: 数字のRSVP表示
    # --------------------------------------------------------
    def phase_digit_display(self, num_digits):
        """指定された桁数の数字を高速表示"""
        self.digit_sequence = generate_digit_sequence(num_digits)

        # 注視点（1秒）
        self.screen.fill(SCREEN_BG_COLOR)
        pygame.draw.circle(self.screen, (255, 255, 255),
                           (self.width // 2, self.height // 2), 3)
        pygame.display.flip()
        pygame.time.wait(1000)

        for digit in self.digit_sequence:
            # 数字表示
            self.screen.fill(SCREEN_BG_COLOR)
            self.draw_text_centered(str(digit), self.digit_font, DIGIT_LUMINANCE_RGB)
            pygame.display.flip()

            t0 = pygame.time.get_ticks()
            while pygame.time.get_ticks() - t0 < DIGIT_DISPLAY_TIME_MS:
                self.handle_quit_events()
                self.clock.tick(FPS)

            # ブランク
            self.screen.fill(SCREEN_BG_COLOR)
            pygame.display.flip()

            t0 = pygame.time.get_ticks()
            while pygame.time.get_ticks() - t0 < DIGIT_BLANK_TIME_MS:
                self.handle_quit_events()
                self.clock.tick(FPS)

        # 表示後の空白
        self.screen.fill(SCREEN_BG_COLOR)
        pygame.display.flip()
        pygame.time.wait(500)

    # --------------------------------------------------------
    # フェーズ 2: 空白画面で待機（DRDの代わり）
    # --------------------------------------------------------
    def phase_wait(self):
        """config の drd.duration_sec 秒間、黒画面で待機する"""
        self.screen.fill(SCREEN_BG_COLOR)
        pygame.display.flip()

        duration_ms = int(WAIT_DURATION_SEC * 1000)
        t0 = pygame.time.get_ticks()

        while pygame.time.get_ticks() - t0 < duration_ms:
            self.handle_quit_events()
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # フェーズ 3: 数字入力画面（桁数可変グリッド）
    # --------------------------------------------------------
    def phase_input(self, num_digits):
        """INPUT_SLOTSマスに数字を入力させる（Enterで入力完了）"""
        input_slots = INPUT_SLOTS
        self.user_responses = [None] * input_slots
        pos = 0
        cursor_visible = True
        cursor_timer = pygame.time.get_ticks()
        input_start = pygame.time.get_ticks()

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    elif len(event.unicode) == 1 and event.unicode in '0123456789':
                        if pos < input_slots:
                            self.user_responses[pos] = event.unicode
                            pos += 1
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if pos > 0:
                            self.response_time_ms = pygame.time.get_ticks() - input_start
                            return

            now = pygame.time.get_ticks()
            if now - cursor_timer >= CURSOR_BLINK_MS:
                cursor_visible = not cursor_visible
                cursor_timer = now

            # --- 描画 ---
            self.screen.fill(SCREEN_BG_COLOR)
            self.draw_text_centered("数字を入力してください", self.label_font,
                                    (255, 255, 255), -100)

            # グリッド
            cell = 50
            gap = 8
            tw = input_slots * cell + (input_slots - 1) * gap
            sx = (self.width - tw) // 2
            gy = self.height // 2 - cell // 2

            for i in range(input_slots):
                cx = sx + i * (cell + gap)
                if i == pos:
                    bd_c = (255, 255, 255) if cursor_visible else (0, 0, 0)
                    width_px = 2
                else:
                    bd_c = (255, 255, 255)
                    width_px = 1

                pygame.draw.rect(self.screen, bd_c, (cx, gy, cell, cell), width_px)

                val = self.user_responses[i]
                if val is not None:
                    txt = self.input_font.render(val, True, (255, 255, 255))
                    self.screen.blit(txt, txt.get_rect(
                        center=(cx + cell // 2, gy + cell // 2)))

            if pos > 0:
                self.draw_text_centered("Enterキーで確定", self.small_font, (255, 255, 255), cell + 40)

            pygame.display.flip()
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # 結果集計（フィードバックなし）
    # --------------------------------------------------------
    def collect_results(self):
        """試行結果を記録する（画面表示なし）"""
        trial = self.trial_list[self.current_trial_idx]
        num_digits = trial["num_digits"]

        correct_str = "".join(map(str, self.digit_sequence))
        # 入力をまとめる（スキップは空白）
        input_chars = []
        for r in self.user_responses:
            if r is None or r == " ":
                input_chars.append(" ")
            else:
                input_chars.append(r)
        input_str = "".join(input_chars)

        correct_count = 0
        for i in range(min(len(correct_str), len(input_str))):
            if correct_str[i] == input_str[i]:
                correct_count += 1

        accuracy = (correct_count / num_digits) * 100 if num_digits > 0 else 0

        result = {
            "subject_no": self.subject_no,
            "block": trial["block"],
            "trial": self.current_trial_idx + 1,
            "num_digits": num_digits,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "digit_sequence": correct_str,
            "user_input": input_str,
            "correct_count": correct_count,
            "total_digits": num_digits,
            "accuracy": accuracy,
            "response_time_ms": self.response_time_ms,
            "wait_duration_sec": WAIT_DURATION_SEC,
            "digit_display_time_ms": DIGIT_DISPLAY_TIME_MS,
            "digit_blank_time_ms": DIGIT_BLANK_TIME_MS,
        }
        self.all_results.append(result)

    # --------------------------------------------------------
    # 結果をCSVに保存
    # --------------------------------------------------------
    def save_results(self):
        """全試行の結果をCSVファイルに保存"""
        if not self.all_results:
            return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(base_dir, "preliminary_results")
        os.makedirs(results_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(results_dir,
                                f"preliminary_subject{self.subject_no}_{timestamp}.csv")

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.all_results[0].keys())
            writer.writeheader()
            for row in self.all_results:
                writer.writerow(row)

        print(f"結果を {filename} に保存しました。（{len(self.all_results)}試行分）")

    # --------------------------------------------------------
    # 終了画面
    # --------------------------------------------------------
    def phase_end_screen(self):
        """実験終了画面"""
        self.screen.fill(SCREEN_BG_COLOR)
        self.draw_text_centered("実験終了", self.title_font, (255, 255, 255), -30)
        self.draw_text_centered("お疲れ様でした。Escキーで終了します。",
                                self.small_font, (180, 180, 180), 30)
        pygame.display.flip()

        while True:
            event = self.handle_quit_events()
            if event and event.type == pygame.KEYDOWN:
                break
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # 実験の実行
    # --------------------------------------------------------
    def run(self):
        """実験全体を実行する"""
        # 全試行条件を生成
        self.trial_list = generate_trial_list()

        for idx in range(TOTAL_TRIALS):
            self.current_trial_idx = idx
            trial = self.trial_list[idx]
            num_digits = trial["num_digits"]

            # 開始画面
            self.phase_start_screen()

            # フェーズ1: RSVP数字表示
            self.phase_digit_display(num_digits)

            # フェーズ2: 空白画面で待機（DRDの代わり）
            self.phase_wait()

            # フェーズ3: 数字入力
            self.phase_input(num_digits)

            # 結果集計（フィードバックなし）
            self.collect_results()

        # 全試行終了後にCSV保存
        self.save_results()

        # 終了画面
        self.phase_end_screen()

        pygame.quit()
        print("予備実験を終了しました。")


# ============================================================
# メイン
# ============================================================

if __name__ == "__main__":
    experiment = PreliminaryExperiment()
    experiment.run()
