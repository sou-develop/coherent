"""
コヒーレント運動実験プログラム

実験フロー:
1. 数字を1つずつ画面中央に高速表示（RSVP）— 桁数は試行ごとに6〜9桁
2. コヒーレント運動（動的ランダムドット: DRD）を表示
3. 記憶した数字の入力画面を表示（固定マス数、Enterで途中確定可）

試行構成:
- 2方向 × 5コヒーレンス率 × 4桁数(6-9) = 全40条件を1回ずつ（合計40試行）
- 順序はランダム、フィードバックなし

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
PIXELS_PER_DEGREE = _display.get("pixels_per_degree", 32)

# --- RSVP設定 ---
_rsvp = _config.get("rsvp", {})
DIGIT_DISPLAY_TIME_MS = _rsvp.get("digit_display_time_ms", 500)
DIGIT_BLANK_TIME_MS = _rsvp.get("digit_blank_time_ms", 100)
DIGIT_LENGTHS_MIN = _rsvp.get("digit_lengths_min", 6)
DIGIT_LENGTHS_MAX = _rsvp.get("digit_lengths_max", 9)
INPUT_SLOTS = _rsvp.get("input_slots", 10)
DIGIT_FONT_SIZE = _rsvp.get("digit_font_size", 120)
DIGIT_VISUAL_ANGLE_DEG = _rsvp.get("digit_visual_angle_deg", 1.0)
BG_DIAMETER_DEG = _rsvp.get("background_diameter_deg", 10)
BG_LUMINANCE_RGB = tuple(_rsvp.get("background_luminance_rgb", [5, 5, 5]))
FRAME_DIAMETER_DEG = _rsvp.get("frame_diameter_deg", 1)
FRAME_LUMINANCE_RGB = tuple(_rsvp.get("frame_luminance_rgb", [100, 100, 100]))
DIGIT_LUMINANCE_RGB = tuple(_rsvp.get("digit_luminance_rgb", [165, 165, 165]))

# --- DRD設定 ---
_drd = _config.get("drd", {})
DRD_DURATION_SEC = _drd.get("duration_sec", 8.0)
DOT_DENSITY_PER_DEG2 = _drd.get("dot_density_per_deg2", 1.27)
DOT_SPEED_DEG_PER_SEC = _drd.get("dot_speed_deg_per_sec", 14.2)
DOT_RADIUS = _drd.get("dot_radius", 3)
DOT_COLOR = tuple(_drd.get("dot_color", [255, 255, 255]))
SIGNAL_DIRECTIONS_DEG = _drd.get("signal_directions_deg", [0, 180])
COHERENCE_LEVELS = _drd.get("coherence_levels", [0.0, 0.05, 0.10, 0.20, 0.50])
REPETITIONS = _drd.get("repetitions_per_condition", 20)

# --- 入力画面設定 ---
_input_cfg = _config.get("input", {})
INPUT_FONT_SIZE = _input_cfg.get("font_size", 48)
INPUT_COLOR = tuple(_input_cfg.get("color", [255, 255, 255]))
CURSOR_BLINK_MS = _input_cfg.get("cursor_blink_ms", 500)

# --- 視角パラメータ（モニター情報から計算） ---
VIEWING_DISTANCE_CM = _display.get("viewing_distance_cm", 70)
DISPLAY_AREA_H_MM = _display.get("display_area_h_mm", 527.04)

# 1ピクセルあたりの物理サイズ = 表示面積(mm) ÷ 解像度(px)
PIXEL_SIZE_MM = DISPLAY_AREA_H_MM / SCREEN_WIDTH

# 視角 → ピクセル変換:
#   size_mm = 2 * distance_mm * tan(angle_deg / 2)
#   size_px = size_mm / pixel_size_mm
DIGIT_TARGET_SIZE_PX = 2 * (VIEWING_DISTANCE_CM * 10) * math.tan(
    math.radians(DIGIT_VISUAL_ANGLE_DEG / 2)
) / PIXEL_SIZE_MM

# --- 計算値 ---
BG_RADIUS_PX = int(BG_DIAMETER_DEG / 2 * PIXELS_PER_DEGREE)
FRAME_RADIUS_PX = int(FRAME_DIAMETER_DEG / 2 * PIXELS_PER_DEGREE)
DRD_APERTURE_RADIUS_PX = BG_RADIUS_PX
DRD_AREA_DEG2 = math.pi * (BG_DIAMETER_DEG / 2) ** 2
NUM_DOTS = round(DOT_DENSITY_PER_DEG2 * DRD_AREA_DEG2)
DOT_SPEED = DOT_SPEED_DEG_PER_SEC * PIXELS_PER_DEGREE / FPS
DIGIT_LENGTHS = list(range(DIGIT_LENGTHS_MIN, DIGIT_LENGTHS_MAX + 1))
TOTAL_TRIALS = len(SIGNAL_DIRECTIONS_DEG) * len(COHERENCE_LEVELS) * len(DIGIT_LENGTHS)  # 2方向 × 5コヒーレンス率 × 4桁数 = 40
SCREEN_BG_COLOR = (0, 0, 0)


# ============================================================
# ユーティリティ
# ============================================================

def generate_digit_sequence(length):
    """ランダムな数字列を生成する"""
    return [random.randint(0, 9) for _ in range(length)]


def deg_to_rad(deg):
    """度をラジアンに変換"""
    return deg * math.pi / 180.0


def generate_trial_list():
    """全試行の条件リストを生成してランダムシャッフル。

    2方向 × 5コヒーレンス率 × 4桁数(6-9) = 全40条件を1回ずつ含む。
    """
    trials = []
    for direction in SIGNAL_DIRECTIONS_DEG:
        for coherence in COHERENCE_LEVELS:
            for num_digits in DIGIT_LENGTHS:
                trials.append({
                    "direction_deg": direction,
                    "coherence": coherence,
                    "num_digits": num_digits,
                })
    random.shuffle(trials)
    return trials


# ============================================================
# ドットクラス（DRD用）
# ============================================================

class Dot:
    """動的ランダムドットの個々のドット"""

    def __init__(self, cx, cy, aperture_radius, speed, coherent_direction_rad):
        self.cx = cx
        self.cy = cy
        self.aperture_radius = aperture_radius
        self.speed = speed
        self.coherent_direction_rad = coherent_direction_rad
        self._randomize_position()
        # ノイズ時に使う固有のランダム方向（直線運動）
        self.noise_direction = random.uniform(0, 2 * math.pi)

    def _randomize_position(self):
        """円形アパーチャ内のランダムな位置に配置"""
        angle = random.uniform(0, 2 * math.pi)
        r = self.aperture_radius * math.sqrt(random.random())
        self.x = self.cx + r * math.cos(angle)
        self.y = self.cy + r * math.sin(angle)

    def _wrap_around(self, direction):
        """アパーチャ端に達したドットを、移動方向の反対側の端から再入場させる"""
        dx = self.x - self.cx
        dy = self.y - self.cy
        d_cos = math.cos(direction)
        d_sin = math.sin(direction)
        # 移動方向への射影（縦成分）
        proj = dx * d_cos + dy * d_sin
        # 移動方向に垂直な成分（横成分）
        perp_x = dx - proj * d_cos
        perp_y = dy - proj * d_sin
        perp_dist_sq = perp_x * perp_x + perp_y * perp_y

        if perp_dist_sq < self.aperture_radius * self.aperture_radius:
            # 横成分を保ったまま、反対側の縁から再入
            along = math.sqrt(self.aperture_radius * self.aperture_radius - perp_dist_sq)
            self.x = self.cx + perp_x - along * d_cos
            self.y = self.cy + perp_y - along * d_sin
        else:
            self._randomize_position()

    def update(self, is_coherent):
        """ドットを移動させる

        シグナルドット: 信号方向に一直線に移動
        ノイズドット:   固有のランダム方向に一直線に移動
        どちらもアパーチャ端に達したら反対側から再入場する。
        """
        if is_coherent:
            direction = self.coherent_direction_rad
        else:
            direction = self.noise_direction

        self.x += self.speed * math.cos(direction)
        self.y += self.speed * math.sin(direction)

        dx = self.x - self.cx
        dy = self.y - self.cy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > self.aperture_radius:
            self._wrap_around(direction)
            # ノイズドットは再入場時に新しいランダム方向を割り当てる
            if not is_coherent:
                self.noise_direction = random.uniform(0, 2 * math.pi)

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

        self.digit_font = self._compute_digit_font(get_font)
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
        self.current_coherence = 0.0
        self.current_direction_deg = 0.0

    # --------------------------------------------------------
    # 視角ベースのフォントサイズ計算
    # --------------------------------------------------------
    def _compute_digit_font(self, get_font_func):
        """視角 DIGIT_VISUAL_ANGLE_DEG（直径）に数字が収まるフォントを計算する。

        pygame のフォントサイズ（ポイント）は文字の描画高さと一致しないため、
        実際にレンダリングして高さを測定し、目標ピクセル数に最も近いサイズを
        二分探索で求める。

        目標ピクセル数: DIGIT_TARGET_SIZE_PX（≈44.5px @ 視角1°, 距離70cm）
        """
        target_px = DIGIT_TARGET_SIZE_PX
        test_chars = "0123456789"

        def measure_max_height(font_size):
            font = get_font_func(font_size)
            max_h = 0
            for ch in test_chars:
                surf = font.render(ch, True, (255, 255, 255))
                max_h = max(max_h, surf.get_height())
            return max_h, font

        lo, hi = 8, 200
        best_font = get_font_func(DIGIT_FONT_SIZE)
        best_diff = float('inf')

        while lo <= hi:
            mid = (lo + hi) // 2
            h, font = measure_max_height(mid)
            diff = abs(h - target_px)
            if diff < best_diff:
                best_diff = diff
                best_font = font
                best_size = mid
            if h < target_px:
                lo = mid + 1
            elif h > target_px:
                hi = mid - 1
            else:
                break

        print(f"[視角設定] 目標: 視角{DIGIT_VISUAL_ANGLE_DEG}° = {target_px:.1f}px, "
              f"フォントサイズ: {best_size}pt, "
              f"実測高さ: {measure_max_height(best_size)[0]}px")
        return best_font

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

    def draw_bg_circle(self):
        """直径10度の黒い背景円"""
        pygame.draw.circle(self.screen, BG_LUMINANCE_RGB,
                           (self.width // 2, self.height // 2), BG_RADIUS_PX)

    def draw_frame_circle(self):
        """直径1度の暗灰色の提示枠（輪郭のみ）"""
        pygame.draw.circle(self.screen, FRAME_LUMINANCE_RGB,
                           (self.width // 2, self.height // 2), FRAME_RADIUS_PX, 1)

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
        """指定された桁数の数字を高速表示（背景円＋提示枠付き）"""
        self.digit_sequence = generate_digit_sequence(num_digits)

        # 注視点（1秒）: 黒背景に点のみ
        self.screen.fill(SCREEN_BG_COLOR)
        pygame.draw.circle(self.screen, (255, 255, 255),
                           (self.width // 2, self.height // 2), 3)
        pygame.display.flip()
        pygame.time.wait(1000)

        for digit in self.digit_sequence:
            # 数字表示 (背景は純黒にして薄い丸が出ないように)
            self.screen.fill(SCREEN_BG_COLOR)
            self.draw_text_centered(str(digit), self.digit_font, DIGIT_LUMINANCE_RGB)
            pygame.display.flip()

            t0 = pygame.time.get_ticks()
            while pygame.time.get_ticks() - t0 < DIGIT_DISPLAY_TIME_MS:
                self.handle_quit_events()
                self.clock.tick(FPS)

            # ブランク: 黒のみ（余計なマークなし）
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
    # フェーズ 2: DRD表示
    # --------------------------------------------------------
    def phase_coherent_motion(self):
        """DRDを背景円内に表示"""
        cx, cy = self.width // 2, self.height // 2
        trial = self.trial_list[self.current_trial_idx]
        coherence = trial["coherence"]
        direction_deg = trial["direction_deg"]
        self.current_coherence = coherence
        self.current_direction_deg = direction_deg
        coherent_dir_rad = deg_to_rad(direction_deg)

        dots = []
        num_coherent = int(round(NUM_DOTS * coherence))
        for i in range(NUM_DOTS):
            dots.append(Dot(cx, cy, DRD_APERTURE_RADIUS_PX, DOT_SPEED,
                            coherent_dir_rad))

        # シグナル/ノイズの割り当てを固定（最初のnum_coherent個がシグナル）
        random.shuffle(dots)
        is_coherent_flags = [i < num_coherent for i in range(NUM_DOTS)]

        t0 = pygame.time.get_ticks()
        duration_ms = int(DRD_DURATION_SEC * 1000)

        while pygame.time.get_ticks() - t0 < duration_ms:
            self.handle_quit_events()
            self.screen.fill(SCREEN_BG_COLOR)
            self.draw_bg_circle()

            for i, dot in enumerate(dots):
                dot.update(is_coherent_flags[i])
                dot.draw(self.screen)
                
            pygame.display.flip()
            self.clock.tick(FPS)

        self.screen.fill(SCREEN_BG_COLOR)
        pygame.display.flip()
        pygame.time.wait(500)

    # --------------------------------------------------------
    # フェーズ 3: 数字入力画面（固定マスグリッド＋Enter途中確定）
    # --------------------------------------------------------
    def phase_input(self):
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
            "trial": self.current_trial_idx + 1,
            "num_digits": num_digits,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "digit_sequence": correct_str,
            "user_input": input_str,
            "correct_count": correct_count,
            "total_digits": num_digits,
            "accuracy": accuracy,
            "response_time_ms": self.response_time_ms,
            "coherence": self.current_coherence,
            "direction_deg": self.current_direction_deg,
            "drd_duration_sec": DRD_DURATION_SEC,
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
        results_dir = os.path.join(base_dir, "results")
        os.makedirs(results_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(results_dir,
                                f"subject{self.subject_no}_{timestamp}.csv")

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
        pygame.event.clear()
        self.screen.fill(SCREEN_BG_COLOR)
        self.draw_text_centered("終了", self.title_font, (255, 255, 255), 0)
        pygame.display.flip()

        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    waiting = False
                    break
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        waiting = False
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

            # フェーズ2: DRD表示
            self.phase_coherent_motion()

            # フェーズ3: 数字入力
            self.phase_input()

            # 結果集計（フィードバックなし）
            self.collect_results()

        # 全試行終了後にCSV保存
        self.save_results()

        # 終了画面
        self.phase_end_screen()

        pygame.quit()
        print("実験を終了しました。")


# ============================================================
# メイン
# ============================================================

if __name__ == "__main__":
    experiment = CoherentMotionExperiment()
    experiment.run()
