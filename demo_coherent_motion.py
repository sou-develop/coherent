"""
コヒーレント運動（DRD）確認用デモプログラム

本実験と同じ計算方法・パラメータを使用して、コヒーレント運動を画面に連続表示します。
キーボード操作でコヒーレンス率や方向をリアルタイムに切り替えて確認できます。

操作方法:
- [↑] [↓] キー : コヒーレンス率の変更
- [←] [→] キー : 運動方向（左/右）の変更
- [W] [S] キー : 速度の変更（本実験には影響しません）
- [ESC] キー : 終了

使い方:
  python3 demo_coherent_motion.py
"""

import pygame
import random
import math
import sys
import os
import json

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
DOT_DENSITY_PER_DEG2 = _drd.get("dot_density_per_deg2", 1.27)
DOT_SPEED_DEG_PER_SEC = _drd.get("dot_speed_deg_per_sec", 14.2)
DOT_RADIUS = _drd.get("dot_radius", 3)
DOT_COLOR = tuple(_drd.get("dot_color", [255, 255, 255]))
SIGNAL_DIRECTIONS_DEG = _drd.get("signal_directions_deg", [0, 180])
COHERENCE_LEVELS = _drd.get("coherence_levels", [0.0, 0.05, 0.10, 0.20, 0.50])

# --- 背景円設定（本実験と共有） ---
_rsvp = _config.get("rsvp", {})
BG_DIAMETER_DEG = _rsvp.get("background_diameter_deg", 10)
BG_LUMINANCE_RGB = tuple(_rsvp.get("background_luminance_rgb", [15, 15, 15]))

# --- 視角パラメータ（モニター情報から計算） ---
VIEWING_DISTANCE_CM = _display.get("viewing_distance_cm", 70)
DISPLAY_AREA_H_MM = _display.get("display_area_h_mm", 527.04)
PIXEL_SIZE_MM = DISPLAY_AREA_H_MM / SCREEN_WIDTH

# --- 計算値 ---
# 背景円の直径（視角 → ピクセル変換: tan() ベースの計算）
BG_DIAMETER_PX = 2 * (VIEWING_DISTANCE_CM * 10) * math.tan(
    math.radians(BG_DIAMETER_DEG / 2)
) / PIXEL_SIZE_MM
BG_RADIUS_PX = int(BG_DIAMETER_PX / 2)
DRD_APERTURE_RADIUS_PX = BG_RADIUS_PX
DRD_AREA_DEG2 = math.pi * (BG_DIAMETER_DEG / 2) ** 2
NUM_DOTS = round(DOT_DENSITY_PER_DEG2 * DRD_AREA_DEG2)

# 1度あたりのピクセル数（tan ベース, 1°）
_PIXELS_PER_DEG_EXACT = 2 * (VIEWING_DISTANCE_CM * 10) * math.tan(
    math.radians(0.5)
) / PIXEL_SIZE_MM
DOT_SPEED = DOT_SPEED_DEG_PER_SEC * _PIXELS_PER_DEG_EXACT / FPS
SCREEN_BG_COLOR = (0, 0, 0)


def deg_to_rad(deg):
    return deg * math.pi / 180.0


# ============================================================
# ドットクラス（DRD用）
# ============================================================

class Dot:
    """動的ランダムドットの個々のドット"""

    def __init__(self, cx, cy, aperture_radius, speed):
        self.cx = cx
        self.cy = cy
        self.aperture_radius = aperture_radius
        self.speed = speed
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

    def update(self, is_coherent, coherent_direction_rad):
        """ドットを移動させる"""
        if is_coherent:
            direction = coherent_direction_rad
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
# メイン
# ============================================================

def main():
    pygame.init()
    if FULLSCREEN:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        width, height = screen.get_size()
    else:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        width, height = SCREEN_WIDTH, SCREEN_HEIGHT

    pygame.display.set_caption("コヒーレント運動 デモ")
    
    # マウスは見えるままにする（デモなので）
    pygame.mouse.set_visible(True)
    clock = pygame.time.Clock()

    # フォント設定
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

    font_large = get_font(36)
    font_small = get_font(24)

    # 状態変数
    coherence_idx = len(COHERENCE_LEVELS) - 1  # 最初は一番高いコヒーレンス
    direction_idx = 0
    speed_multiplier = 1.0  # デモ用の速度倍率
    
    # ドットの初期化
    cx, cy = width // 2, height // 2
    dots = [Dot(cx, cy, DRD_APERTURE_RADIUS_PX, DOT_SPEED) for _ in range(NUM_DOTS)]

    running = True
    while running:
        # パラメータ取得
        coherence = COHERENCE_LEVELS[coherence_idx]
        direction_deg = SIGNAL_DIRECTIONS_DEG[direction_idx]
        coherent_dir_rad = deg_to_rad(direction_deg)
        
        # シグナル/ノイズの判定
        num_coherent = int(round(NUM_DOTS * coherence))
        # 毎回シャッフルしない。一度決めたシグナルドットの役割はデモ中固定する
        # （これによりリアルタイムなコヒーレンス変更でもチラつきにくい）
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP:
                    coherence_idx = min(coherence_idx + 1, len(COHERENCE_LEVELS) - 1)
                elif event.key == pygame.K_DOWN:
                    coherence_idx = max(coherence_idx - 1, 0)
                elif event.key == pygame.K_LEFT:
                    direction_idx = (direction_idx - 1) % len(SIGNAL_DIRECTIONS_DEG)
                elif event.key == pygame.K_RIGHT:
                    direction_idx = (direction_idx + 1) % len(SIGNAL_DIRECTIONS_DEG)
                elif event.key == pygame.K_w:
                    speed_multiplier += 0.5
                elif event.key == pygame.K_s:
                    speed_multiplier = max(0.5, speed_multiplier - 0.5)

        # 速度の更新
        for dot in dots:
            dot.speed = DOT_SPEED * speed_multiplier

        # 描画開始
        screen.fill(SCREEN_BG_COLOR)
        
        # 背景円
        pygame.draw.circle(screen, BG_LUMINANCE_RGB, (cx, cy), BG_RADIUS_PX)

        # ドットの更新と描画
        for i, dot in enumerate(dots):
            is_coherent = (i < num_coherent)
            dot.update(is_coherent, coherent_dir_rad)
            dot.draw(screen)

        # UI描画
        ui_color = (200, 200, 200)
        margin_x, margin_y = 30, 30
        
        text_dir = "右" if direction_deg == 0 else "左" if direction_deg == 180 else f"{direction_deg}°"
        
        lines = [
            "コヒーレント運動 デモ (終了: ESC)",
            f"コヒーレンス率 [↑/↓]: {coherence * 100:.1f} %",
            f"運動方向     [←/→]: {text_dir}",
            f"運動速度     [W / S]: {speed_multiplier:.1f} 倍"
        ]
        
        for i, line in enumerate(lines):
            f = font_large if i > 0 else font_small
            surf = f.render(line, True, ui_color)
            screen.blit(surf, (margin_x, margin_y + i * 40))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()
