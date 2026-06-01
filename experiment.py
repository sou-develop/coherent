"""
コヒーレント運動実験プログラム

実験フロー:
1. 15桁の数字を1つずつ画面中央に高速表示（RSVP）
2. コヒーレント運動（ランダムドットキネマトグラム）を8秒間表示
3. 記憶した数字の入力画面を表示

使い方:
  python3 experiment.py
"""

import pygame
import random
import math
import sys
import os
import csv
import json
from datetime import datetime

# ============================================================
# 設定ファイル読み込み
# ============================================================

def load_config():
    """config.json から設定を読み込む"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_config = load_config()

# ============================================================
# 設定パラメータ（config.json で上書き可能）
# ============================================================

# --- 画面設定 ---
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
FULLSCREEN = False  # True にするとフルスクリーン
BG_COLOR = (30, 30, 30)  # 背景色（ダークグレー）

# --- 数字表示（RSVP）設定 ---
NUM_DIGITS = _config.get("num_digits", 15)
DIGIT_DISPLAY_TIME_MS = _config.get("digit_display_time_ms", 1500)
DIGIT_BLANK_TIME_MS = _config.get("digit_blank_time_ms", 100)
DIGIT_FONT_SIZE = 120  # 数字のフォントサイズ
DIGIT_COLOR = (255, 255, 255)  # 数字の色（白）

# --- コヒーレント運動設定 ---
COHERENT_DURATION_SEC = _config.get("coherent_duration_sec", 8.0)
NUM_DOTS = _config.get("num_dots", 200)
DOT_RADIUS = 3  # ドットの半径（ピクセル）
DOT_COLOR = (255, 255, 255)  # ドットの色（白）
DOT_SPEED = _config.get("dot_speed", 3.0)
COHERENCE = _config.get("coherence", 0.5)
DOT_LIFETIME = 0  # ドットの寿命（0で無限 = リロードしない）

# コヒーレント方向（度、0=右、90=上、180=左、270=下）
COHERENT_DIRECTION_DEG = _config.get("coherent_direction_deg", 0)

# --- 入力画面設定 ---
INPUT_FONT_SIZE = 48
INPUT_COLOR = (255, 255, 255)
CURSOR_BLINK_MS = 500  # カーソル点滅間隔

# --- フレームレート ---
FPS = 60


# ============================================================
# ユーティリティ
# ============================================================

def generate_digit_sequence(length):
    """ランダムな数字列を生成する"""
    return [random.randint(0, 9) for _ in range(length)]


def deg_to_rad(deg):
    """度をラジアンに変換"""
    return deg * math.pi / 180.0


# ============================================================
# ドットクラス（コヒーレント運動用）
# ============================================================

class Dot:
    """ランダムドットキネマトグラムの個々のドット"""

    def __init__(self, cx, cy, aperture_radius, speed, coherent_direction_rad, is_coherent):
        self.cx = cx
        self.cy = cy
        self.aperture_radius = aperture_radius
        self.speed = speed
        self.coherent_direction_rad = coherent_direction_rad
        self.is_coherent = is_coherent
        self.lifetime = 0

        # ランダムな初期位置（円形アパーチャ内）
        self._randomize_position()

        # 方向を決定
        if self.is_coherent:
            self.direction = self.coherent_direction_rad
        else:
            self.direction = random.uniform(0, 2 * math.pi)

    def _randomize_position(self):
        """円形アパーチャ内のランダムな位置に配置"""
        angle = random.uniform(0, 2 * math.pi)
        r = self.aperture_radius * math.sqrt(random.random())
        self.x = self.cx + r * math.cos(angle)
        self.y = self.cy + r * math.sin(angle)

    def update(self):
        """ドットを移動させる"""
        self.x += self.speed * math.cos(self.direction)
        self.y += self.speed * math.sin(self.direction)
        self.lifetime += 1

        # アパーチャの外に出たら反対側にラップアラウンド
        dx = self.x - self.cx
        dy = self.y - self.cy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > self.aperture_radius:
            # 反対側に配置
            self.x = self.cx - dx * 0.9
            self.y = self.cy - dy * 0.9
            # アパーチャ内に収める
            dx2 = self.x - self.cx
            dy2 = self.y - self.cy
            dist2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
            if dist2 > self.aperture_radius:
                self._randomize_position()

    def draw(self, surface):
        """ドットを描画"""
        pygame.draw.circle(surface, DOT_COLOR, (int(self.x), int(self.y)), DOT_RADIUS)


# ============================================================
# 実験メインクラス
# ============================================================

class CoherentMotionExperiment:
    """コヒーレント運動実験のメインクラス"""

    def __init__(self):
        pygame.init()

        if FULLSCREEN:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.width, self.height = self.screen.get_size()
        else:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.width = SCREEN_WIDTH
            self.height = SCREEN_HEIGHT

        pygame.display.set_caption("コヒーレント運動実験")
        self.clock = pygame.time.Clock()

        # フォントの初期化（フォントファイルを直接指定してクロスプラットフォーム対応）
        FONT_FILE_CANDIDATES = [
            # macOS
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            # Windows
            "C:/Windows/Fonts/yugothic.ttf",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            # Linux
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        ]

        def find_font_path():
            for path in FONT_FILE_CANDIDATES:
                if os.path.exists(path):
                    return path
            return None

        font_path = find_font_path()

        def get_font(size):
            if font_path:
                try:
                    return pygame.font.Font(font_path, size)
                except:
                    pass
            return pygame.font.Font(None, size)

        self.digit_font = get_font(DIGIT_FONT_SIZE)
        self.fixation_font = get_font(36)  # 注視点用の小さいフォント
        self.input_font = get_font(INPUT_FONT_SIZE)
        self.label_font = get_font(32)
        self.small_font = get_font(24)
        self.title_font = get_font(56)

        # 実験データ
        self.digit_sequence = []
        self.user_input = ""
        self.results = {}
        self.response_time_ms = 0  # 反応時間（ミリ秒）

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

    def wait_for_key(self):
        """キー入力を待つ"""
        while True:
            event = self.handle_quit_events()
            if event and event.type == pygame.KEYDOWN:
                return event
            self.clock.tick(FPS)

    def draw_text_centered(self, text, font, color, y_offset=0):
        """テキストを画面中央に描画"""
        surface = font.render(text, True, color)
        rect = surface.get_rect(center=(self.width // 2, self.height // 2 + y_offset))
        self.screen.blit(surface, rect)

    # --------------------------------------------------------
    # フェーズ 0: 開始画面
    # --------------------------------------------------------
    def phase_start_screen(self):
        """開始画面を表示（スペースキーで開始のみ）"""
        self.screen.fill(BG_COLOR)

        # スペースキーで開始の案内のみ表示
        self.draw_text_centered("スペースキーで開始", self.label_font, (255, 220, 100), 0)

        pygame.display.flip()

        # スペースキーを待つ
        while True:
            event = self.handle_quit_events()
            if event and event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                break
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # フェーズ 1: 数字のRSVP表示
    # --------------------------------------------------------
    def phase_digit_display(self):
        """15桁の数字を1つずつ高速表示する"""
        self.digit_sequence = generate_digit_sequence(NUM_DIGITS)

        # 開始前の注視点表示（1秒）
        self.screen.fill(BG_COLOR)
        self.draw_text_centered("+", self.fixation_font, (150, 150, 150))
        pygame.display.flip()
        pygame.time.wait(1000)

        # 各数字を順番に表示
        for digit in self.digit_sequence:
            # 数字を表示
            self.screen.fill(BG_COLOR)
            self.draw_text_centered(str(digit), self.digit_font, DIGIT_COLOR)
            pygame.display.flip()

            # 表示時間分待機
            start_time = pygame.time.get_ticks()
            while pygame.time.get_ticks() - start_time < DIGIT_DISPLAY_TIME_MS:
                self.handle_quit_events()
                self.clock.tick(FPS)

            # ブランク画面
            self.screen.fill(BG_COLOR)
            pygame.display.flip()

            start_time = pygame.time.get_ticks()
            while pygame.time.get_ticks() - start_time < DIGIT_BLANK_TIME_MS:
                self.handle_quit_events()
                self.clock.tick(FPS)

        # 数字表示後の短い空白
        self.screen.fill(BG_COLOR)
        pygame.display.flip()
        pygame.time.wait(500)

    # --------------------------------------------------------
    # フェーズ 2: コヒーレント運動表示
    # --------------------------------------------------------
    def phase_coherent_motion(self):
        """コヒーレント運動（ランダムドットキネマトグラム）を画面全体に表示する"""
        cx = self.width // 2
        cy = self.height // 2
        coherent_dir_rad = deg_to_rad(COHERENT_DIRECTION_DEG)

        # 画面全体をカバーする半径（対角線の半分）
        aperture_radius = int(math.sqrt(self.width ** 2 + self.height ** 2) / 2)

        # ドットを生成
        dots = []
        for i in range(NUM_DOTS):
            is_coherent = (i < int(NUM_DOTS * COHERENCE))
            dot = Dot(cx, cy, aperture_radius, DOT_SPEED, coherent_dir_rad, is_coherent)
            dots.append(dot)

        # シャッフルしてコヒーレント/ランダムの区別を見えなくする
        random.shuffle(dots)

        start_time = pygame.time.get_ticks()
        duration_ms = int(COHERENT_DURATION_SEC * 1000)

        while True:
            elapsed = pygame.time.get_ticks() - start_time
            if elapsed >= duration_ms:
                break

            self.handle_quit_events()

            # 背景描画
            self.screen.fill(BG_COLOR)

            # ドットの更新と描画（枠なし）
            for dot in dots:
                dot.update()
                dot.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)

        # 終了後の短い空白
        self.screen.fill(BG_COLOR)
        pygame.display.flip()
        pygame.time.wait(500)

    # --------------------------------------------------------
    # フェーズ 3: 数字入力画面
    # --------------------------------------------------------
    def phase_input(self):
        """ユーザーに覚えた数字を入力させる（反応時間も計測）"""
        self.user_input = ""
        cursor_visible = True
        cursor_timer = pygame.time.get_ticks()
        input_start_time = pygame.time.get_ticks()  # 反応時間計測開始

        while True:
            # イベント処理
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    elif event.key == pygame.K_RETURN:
                        # 入力確定 — 反応時間を記録
                        self.response_time_ms = pygame.time.get_ticks() - input_start_time
                        return
                    elif event.key == pygame.K_BACKSPACE:
                        self.user_input = self.user_input[:-1]
                    elif event.unicode.isdigit():
                        if len(self.user_input) < NUM_DIGITS:
                            self.user_input += event.unicode

            # カーソル点滅
            now = pygame.time.get_ticks()
            if now - cursor_timer >= CURSOR_BLINK_MS:
                cursor_visible = not cursor_visible
                cursor_timer = now

            # 描画
            self.screen.fill(BG_COLOR)

            # タイトル
            self.draw_text_centered("覚えた数字を入力してください", self.label_font, (100, 200, 255), -150)

            # 入力ボックスの描画
            box_width = 600
            box_height = 70
            box_x = (self.width - box_width) // 2
            box_y = self.height // 2 - box_height // 2

            # ボックス背景
            pygame.draw.rect(self.screen, (50, 50, 60), (box_x, box_y, box_width, box_height), border_radius=8)
            # ボックス枠
            pygame.draw.rect(self.screen, (100, 160, 255), (box_x, box_y, box_width, box_height), 2, border_radius=8)

            # 入力テキスト
            display_text = self.user_input
            if cursor_visible:
                display_text += "|"
            text_surface = self.input_font.render(display_text, True, INPUT_COLOR)
            text_rect = text_surface.get_rect(midleft=(box_x + 20, box_y + box_height // 2))
            self.screen.blit(text_surface, text_rect)

            # 入力桁数の表示
            count_text = f"{len(self.user_input)} / {NUM_DIGITS} 桁"
            count_surface = self.small_font.render(count_text, True, (150, 150, 150))
            count_rect = count_surface.get_rect(center=(self.width // 2, box_y + box_height + 30))
            self.screen.blit(count_surface, count_rect)

            # 確定ボタンの案内
            self.draw_text_centered("Enterキーで確定", self.small_font, (255, 220, 100), 120)

            pygame.display.flip()
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # フェーズ 4: 結果表示
    # --------------------------------------------------------
    def phase_results(self):
        """結果を集計し、リトライ/終了の案内のみ表示する"""
        correct_str = "".join(map(str, self.digit_sequence))
        input_str = self.user_input

        # 正答数を計算
        correct_count = 0
        for i in range(min(len(correct_str), len(input_str))):
            if correct_str[i] == input_str[i]:
                correct_count += 1

        accuracy = (correct_count / NUM_DIGITS) * 100 if NUM_DIGITS > 0 else 0

        # 結果を保存
        self.results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "digit_sequence": correct_str,
            "user_input": input_str,
            "correct_count": correct_count,
            "total_digits": NUM_DIGITS,
            "accuracy": accuracy,
            "response_time_ms": self.response_time_ms,
            "coherence": COHERENCE,
            "coherent_duration_sec": COHERENT_DURATION_SEC,
            "digit_display_time_ms": DIGIT_DISPLAY_TIME_MS,
        }

        # フィードバックなし — 操作案内のみ表示
        self.screen.fill(BG_COLOR)
        self.draw_text_centered("スペースキーでもう一度 / Escキーで終了", self.label_font, (255, 220, 100), 0)
        pygame.display.flip()

        # キー待ち
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return False  # 終了
                    elif event.key == pygame.K_SPACE:
                        return True  # もう一度
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # 結果をCSVに保存
    # --------------------------------------------------------
    def save_results(self):
        """結果をCSVファイルに保存"""
        filename = "experiment_results.csv"
        file_exists = os.path.exists(filename)

        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.results.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(self.results)

        print(f"結果を {filename} に保存しました。")

    # --------------------------------------------------------
    # 実験の実行
    # --------------------------------------------------------
    def run(self):
        """実験全体を実行する"""
        while True:
            # 開始画面
            self.phase_start_screen()

            # フェーズ1: 数字表示
            self.phase_digit_display()

            # フェーズ2: コヒーレント運動
            self.phase_coherent_motion()

            # フェーズ3: 数字入力
            self.phase_input()

            # フェーズ4: 結果表示
            repeat = self.phase_results()

            # 結果保存
            self.save_results()

            if not repeat:
                break

        pygame.quit()
        print("実験を終了しました。")


# ============================================================
# メイン
# ============================================================

if __name__ == "__main__":
    experiment = CoherentMotionExperiment()
    experiment.run()
