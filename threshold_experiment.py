"""
コヒーレント運動閾値調査プログラム

実験フロー（1試行）:
1. 「Enterキーで開始」画面
2. 注視点（1秒）
3. コヒーレント運動（DRD）を8秒間表示
4. 黒画面 — 方向判断入力（テンキー4＝左、テンキー6＝右）

試行構成:
- 2方向 × 5コヒーレンス率 = 全10条件 × 20ブロック（合計200試行）
- 順序はランダム（ブロックごとに再シャッフル）、フィードバックなし
- 休憩なし

使い方:
  python3 threshold_experiment.py
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
PIXELS_PER_DEGREE = _display.get("pixels_per_degree", 44.52)

# --- DRD設定 ---
_drd = _config.get("drd", {})
DRD_DURATION_SEC = _drd.get("duration_sec", 8.0)
DOT_DENSITY_PER_DEG2 = _drd.get("dot_density_per_deg2", 1.27)
DOT_SPEED_DEG_PER_SEC = _drd.get("dot_speed_deg_per_sec", 14.2)
DOT_RADIUS = _drd.get("dot_radius", 3)
DOT_COLOR = tuple(_drd.get("dot_color", [255, 255, 255]))
SIGNAL_DIRECTIONS_DEG = _drd.get("signal_directions_deg", [0, 180])
COHERENCE_LEVELS = _drd.get("coherence_levels", [0.0, 0.05, 0.10, 0.20, 0.50])

# --- 閾値調査設定 ---
_threshold = _config.get("threshold", {})
NUM_BLOCKS = _threshold.get("num_blocks", 20)

# --- 背景円設定（本実験と共有） ---
_rsvp = _config.get("rsvp", {})
BG_DIAMETER_DEG = _rsvp.get("background_diameter_deg", 10)
BG_LUMINANCE_RGB = tuple(_rsvp.get("background_luminance_rgb", [15, 15, 15]))

# --- 計算値 ---
BG_RADIUS_PX = int(BG_DIAMETER_DEG / 2 * PIXELS_PER_DEGREE)
DRD_APERTURE_RADIUS_PX = BG_RADIUS_PX
DRD_AREA_DEG2 = math.pi * (BG_DIAMETER_DEG / 2) ** 2
NUM_DOTS = round(DOT_DENSITY_PER_DEG2 * DRD_AREA_DEG2)
DOT_SPEED = DOT_SPEED_DEG_PER_SEC * PIXELS_PER_DEGREE / FPS
CONDITIONS_PER_BLOCK = len(SIGNAL_DIRECTIONS_DEG) * len(COHERENCE_LEVELS)
TOTAL_TRIALS = CONDITIONS_PER_BLOCK * NUM_BLOCKS  # 2×5×20 = 200
SCREEN_BG_COLOR = (0, 0, 0)


# ============================================================
# ユーティリティ
# ============================================================

def deg_to_rad(deg):
    """度をラジアンに変換"""
    return deg * math.pi / 180.0


def generate_block_trials():
    """1ブロック分の条件リストを生成してランダムシャッフル。

    2方向 × 5コヒーレンス率 = 10条件を含む。
    """
    trials = []
    for direction in SIGNAL_DIRECTIONS_DEG:
        for coherence in COHERENCE_LEVELS:
            trials.append({
                "direction_deg": direction,
                "coherence": coherence,
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
# 閾値調査メインクラス
# ============================================================

class ThresholdExperiment:
    """コヒーレント運動閾値調査のメインクラス"""

    def __init__(self):
        pygame.init()
        if FULLSCREEN:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.width, self.height = self.screen.get_size()
        else:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.width = SCREEN_WIDTH
            self.height = SCREEN_HEIGHT

        pygame.display.set_caption("コヒーレント運動閾値調査")
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

        self.fixation_font = get_font(36)
        self.prompt_font = get_font(72)
        self.label_font = get_font(32)
        self.small_font = get_font(24)
        self.title_font = get_font(56)

        # 実験データ
        self.all_results = []
        subject_info = _load_json("subject.json")
        self.subject_no = str(subject_info.get("subject_no", "001"))
        self.trial_list = []
        self.current_trial_idx = 0
        self.current_block = 1
        self.global_trial_idx = 0
        self.current_coherence = 0.0
        self.current_direction_deg = 0.0
        self.user_response_deg = None
        self.response_time_ms = 0

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
        """直径10度の背景円"""
        pygame.draw.circle(self.screen, BG_LUMINANCE_RGB,
                           (self.width // 2, self.height // 2), BG_RADIUS_PX)

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
    # 注視点
    # --------------------------------------------------------
    def phase_fixation(self):
        """注視点（1秒間）"""
        self.screen.fill(SCREEN_BG_COLOR)
        pygame.draw.circle(self.screen, (255, 255, 255),
                           (self.width // 2, self.height // 2), 3)
        pygame.display.flip()
        pygame.time.wait(1000)

    # --------------------------------------------------------
    # コヒーレント運動表示
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

    # --------------------------------------------------------
    # 方向判断入力（黒画面 + テンキー4/6）
    # --------------------------------------------------------
    def phase_direction_input(self):
        """黒画面で方向判断を入力させる。

        テンキー4 = 左（180°）、テンキー6 = 右（0°）。
        """
        # 黒画面に「?」を表示して応答を待つ
        self.screen.fill(SCREEN_BG_COLOR)
        self.draw_text_centered("?", self.prompt_font, (255, 255, 255), 0)
        pygame.display.flip()

        pygame.event.clear()
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
                    if event.key == pygame.K_KP4:
                        self.response_time_ms = pygame.time.get_ticks() - input_start
                        self.user_response_deg = 180  # 左
                        return
                    if event.key == pygame.K_KP6:
                        self.response_time_ms = pygame.time.get_ticks() - input_start
                        self.user_response_deg = 0  # 右
                        return
            self.clock.tick(FPS)

    # --------------------------------------------------------
    # 結果集計（フィードバックなし）
    # --------------------------------------------------------
    def collect_results(self):
        """試行結果を記録する（画面表示なし）"""
        trial = self.trial_list[self.current_trial_idx]
        correct = (self.user_response_deg == trial["direction_deg"])

        result = {
            "subject_no": self.subject_no,
            "block": self.current_block,
            "trial": self.current_trial_idx + 1,
            "global_trial": self.global_trial_idx,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "coherence": trial["coherence"],
            "direction_deg": trial["direction_deg"],
            "response_deg": self.user_response_deg,
            "correct": int(correct),
            "response_time_ms": self.response_time_ms,
            "drd_duration_sec": DRD_DURATION_SEC,
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
                                f"threshold_subject{self.subject_no}_{timestamp}.csv")

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
        """実験全体を実行する（NUM_BLOCKS ブロック × 10条件）"""
        self.global_trial_idx = 0

        for block in range(NUM_BLOCKS):
            self.current_block = block + 1
            # ブロックごとに条件リストを再シャッフル
            self.trial_list = generate_block_trials()

            for idx in range(CONDITIONS_PER_BLOCK):
                self.current_trial_idx = idx
                self.global_trial_idx += 1

                # 開始画面
                self.phase_start_screen()

                # 注視点（1秒）
                self.phase_fixation()

                # コヒーレント運動表示（8秒）
                self.phase_coherent_motion()

                # 黒画面で方向判断入力
                self.phase_direction_input()

                # 結果集計（フィードバックなし）
                self.collect_results()

        # 全試行終了後にCSV保存
        self.save_results()

        # 終了画面
        self.phase_end_screen()

        pygame.quit()
        print("閾値調査を終了しました。")


# ============================================================
# メイン
# ============================================================

if __name__ == "__main__":
    experiment = ThresholdExperiment()
    experiment.run()
