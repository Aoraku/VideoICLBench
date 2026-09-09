#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include <iostream>
#include <vector>

#define DEPTH 3
#define MAXN 100000000
#define R 3
#define J 1

// --- 原版 AI 核心数据结构 ---
int dx4[] = { 0,1,1,1 };
int dy4[] = { 1,1,0,-1 };
int dx8[] = { 0,1,1,1,0,-1,-1,-1 };
int dy8[] = { 1,1,0,-1,-1,-1,0,1 };
int bl[15][15][4] = { 0 };
int bls[15][15][4] = { 0 };
int wt[15][15][4] = { 0 };
int ran[15][15][4][2];
int mark = 0;
int area[15][15] = { 0 };
int huo4[2] = { 0 };

struct pos { int x; int y; };
struct score { int sy; int mk; };

// --- SDL 全局变量 ---
SDL_Window* window = nullptr;
SDL_Renderer* renderer = nullptr;
TTF_Font* font = nullptr;

// ================= 原版 AI 逻辑开始 (完全保留你的算法) =================

int scmp(const score a, score const b) {
	if (a.sy != b.sy) return a.sy - b.sy;
	return a.mk - b.mk;
}

int f(const int k, const int t) {
	if (t) return 0;
	int fu[6] = { 0,1,400,30000,70000,MAXN };
	if (k < 0) return 0;
	return fu[k];
}

bool equ(const int map[15][15], const int x, const int y, const int value) {
	if (x < 0 || y < 0 || x > 14 || y > 14) {
		if (value == -1) return 1;
		else return 0;
	}
	if (value == -1) return 0;
	if (map[x][y] == value) return 1;
	return 0;
}

void loz(int map[15][15], const int x, const int y, const int t) {
	if (map[x][y]) return;
	map[x][y] = t;
	int left = x - R < 0 ? 0 : x - R;
	int right = x + R > 14 ? 14 : x + R;
	int up = y - R < 0 ? 0 : y - R;
	int down = y + R > 14 ? 14 : y + R;
	for (int i = left; i <= right; i++) {
		for (int j = up; j <= down; j++) {
			area[i][j]++;
		}
	}
	if (J && t == 2) {
		for (int i = 0; i < 8; i++) {
			if (!equ(map, x + 5 * dx8[i], y + 5 * dy8[i], -1)) {
				int m = x + 3 * dx8[i], n = y + 3 * dy8[i];
				mark -= f(bl[m][n][i % 4], bls[m][n][i % 4]);
				bls[m][n][i % 4]++;
				if (bl[m][n][i % 4] == 4) huo4[1]--;
			}
		}
	}
	for (int i = 0; i < 4; i++) {
		for (int j = ran[x][y][i][0]; j <= ran[x][y][i][1]; j++) {
			int m = x + j * dx4[i], n = y + j * dy4[i];
			if (t == 1) {
				mark -= f(wt[m][n][i] + 1, 0) - f(wt[m][n][i], 0);
				wt[m][n][i]++;
				if (wt[m][n][i] == 4) huo4[0]++;
				if (bl[m][n][i] == 4) huo4[1]--;
				mark += f(bl[m][n][i] - 4, bls[m][n][i]) - f(bl[m][n][i], bls[m][n][i]);
				bl[m][n][i] -= 4;
			}
			else {
				if (wt[m][n][i] == 4) huo4[0]--;
				mark -= f(wt[m][n][i] - 4, 0) - f(wt[m][n][i], 0);
				wt[m][n][i] -= 4;
				mark += f(bl[m][n][i] + 1, bls[m][n][i]) - f(bl[m][n][i], bls[m][n][i]);
				bl[m][n][i]++;
				if (bl[m][n][i] == 4) huo4[1]++;
			}
		}
	}
}

void tiz(int map[15][15], const int x, const int y, const int t) {
	if (!map[x][y]) return;
	map[x][y] = 0;
	int left = x - R < 0 ? 0 : x - R;
	int right = x + R > 14 ? 14 : x + R;
	int up = y - R < 0 ? 0 : y - R;
	int down = y + R > 14 ? 14 : y + R;
	for (int i = left; i <= right; i++) {
		for (int j = up; j <= down; j++) {
			area[i][j]--;
		}
	}
	if (J && t == 2) {
		for (int i = 0; i < 8; i++) {
			if (!equ(map, x + 5 * dx8[i], y + 5 * dy8[i], -1)) {
				int m = x + 3 * dx8[i], n = y + 3 * dy8[i];
				mark += f(bl[m][n][i % 4], bls[m][n][i % 4] - 1);
				bls[m][n][i % 4]--;
				if (bl[m][n][i % 4] == 4 && !bls[m][n][i % 4]) huo4[1]++;
			}
		}
	}
	for (int i = 0; i < 4; i++) {
		for (int j = ran[x][y][i][0]; j <= ran[x][y][i][1]; j++) {
			int m = x + j * dx4[i], n = y + j * dy4[i];
			if (t == 1) {
				if (wt[m][n][i] == 4) huo4[0]--;
				mark -= f(wt[m][n][i] - 1, 0) - f(wt[m][n][i], 0);
				wt[m][n][i]--;
				mark += f(bl[m][n][i] + 4, bls[m][n][i]) - f(bl[m][n][i], bls[m][n][i]);
				bl[m][n][i] += 4;
				if (bl[m][n][i] == 4) huo4[1]++;
			}
			else {
				mark -= f(wt[m][n][i] + 4, 0) - f(wt[m][n][i], 0);
				wt[m][n][i] += 4;
				if (wt[m][n][i] == 4) huo4[0]++;
				if (bl[m][n][i] == 4) huo4[1]--;
				mark += f(bl[m][n][i] - 1, bls[m][n][i]) - f(bl[m][n][i], bls[m][n][i]);
				bl[m][n][i]--;
			}
		}
	}
}

bool is_jin3(const int map[15][15], const int x, const int y) {
	if (!J) return 0;
	int arr1[] = { 0,2,0,2,2,0 };
	int arr2[] = { 0,2,2,0,2,0 };
	int arr3[] = { 0,2,2,2,0 };
	int h = 0;
	for (int i = 0; i < 4; i++) {
		for (int j = 1; j < 5; j++) {
			if (j == 2) continue;
			bool s = 1;
			for (int k = 0; k < 6; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr1[k])) { s = 0; break; }
			}
			if (s) { h++; if (h > 1) return 1; break; }
		}
		for (int j = 1; j < 5; j++) {
			if (j == 3) continue;
			bool s = 1;
			for (int k = 0; k < 6; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr2[k])) { s = 0; break; }
			}
			if (s) { h++; if (h > 1) return 1; break; }
		}
		for (int j = 1; j < 4; j++) {
			bool s = 1;
			for (int k = 0; k < 5; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr3[k])) { s = 0; break; }
			}
			if (s) {
				if ((equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 0) && !equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 2)) || (equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 0) && !equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 2))) {
					h++; if (h > 1) return 1;
				}
				break;
			}
		}
	}
	return 0;
}

bool is_jin4(const int map[15][15], const int x, const int y) {
	if (!J) return 0;
	int arr1[] = { 2,2,2,0,2 };
	int arr2[] = { 2,0,2,2,2 };
	int arr3[] = { 2,2,0,2,2 };
	int h = 0;
	for (int i = 0; i < 4; i++) {
		for (int j = 0; j < 5; j++) {
			if (j == 3) continue;
			bool s = 1;
			for (int k = 0; k < 5; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr1[k])) { s = 0; break; }
			}
			if (s) {
				if (!equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 2) && !equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 2)) {
					h++; if (h > 1) return 1;
				}
				break;
			}
		}
		for (int j = 0; j < 5; j++) {
			if (j == 1) continue;
			bool s = 1;
			for (int k = 0; k < 5; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr2[k])) { s = 0; break; }
			}
			if (s) {
				if (!equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 2) && !equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 2)) {
					h++; if (h > 1) return 1;
				}
				break;
			}
		}
		for (int j = 0; j < 5; j++) {
			if (j == 2) continue;
			bool s = 1;
			for (int k = 0; k < 5; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], arr3[k])) { s = 0; break; }
			}
			if (s) {
				if (!equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 2) && !equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 2)) {
					h++; if (h > 1) return 1;
				}
			}
		}
		for (int j = 0; j < 4; j++) {
			bool s = 1;
			for (int k = 0; k < 4; k++) {
				if (!equ(map, x + (k - j) * dx4[i], y + (k - j) * dy4[i], 2)) { s = 0; break; }
			}
			if (s) {
				if ((equ(map, x - (1 + j) * dx4[i], y - (1 + j) * dy4[i], 0) && !equ(map, x - (2 + j) * dx4[i], y - (2 + j) * dy4[i], 2)) || (equ(map, x + (4 - j) * dx4[i], y + (4 - j) * dy4[i], 0) && !equ(map, x + (5 - j) * dx4[i], y + (5 - j) * dy4[i], 2))) {
					h++; if (h > 1) return 1;
				}
				break;
			}
		}
	}
	return 0;
}

bool is_5(const int map[15][15], const int x, const int y) {
	int t = map[x][y];
	for (int i = 0; i < 4; i++) {
		for (int j = ran[x][y][i][0]; j <= ran[x][y][i][1]; j++) {
			int m = x + j * dx4[i], n = y + j * dy4[i];
			if ((t == 2 && bl[m][n][i] == 5) || (t == 1 && wt[m][n][i] == 5)) return 1;
		}
	}
	return 0;
}

bool is_jin6(const int map[15][15], const int x, const int y) {
	if (!J) return 0;
	for (int i = 0; i < 4; i++) {
		for (int j = ran[x][y][i][0]; j <= ran[x][y][i][1]; j++) {
			int m = x + j * dx4[i], n = y + j * dy4[i];
			if (bl[m][n][i] == 5 && bls[m][n][i]) return 1;
		}
	}
	return 0;
}

int check_win(const int map[15][15], const int x, const int y) {
	int t = map[x][y];
	if (t == 2 && is_jin6(map, x, y)) return 1; // 黑方禁手，白胜返回1
	if (is_5(map, x, y)) return t; // 正常连五胜，返回颜色 (1白2黑)
	if (t == 2 && (is_jin3(map, x, y) || is_jin4(map, x, y))) return 1; // 黑方禁手，白胜返回1
	return 0;
}

score minimax(int map[15][15], const score brother, const int x, const int y, const int t, const int d) {
	loz(map, x, y, t);
	int mark_s = mark;
	int r = check_win(map, x, y);
	if (t == 2 && r == 1) {
		tiz(map, x, y, t);
		return { -1,mark_s - 4 * MAXN };
	}
	if (r == t) {
		tiz(map, x, y, t);
		return { 2 * t - 3,mark_s + (2 * t - 3) * (DEPTH - d) * MAXN };
	}
	if (huo4[2 - t]) {
		tiz(map, x, y, t);
		return { 3 - 2 * t,mark_s + (3 - 2 * t) * MAXN };
	}
	if (d == DEPTH) {
		tiz(map, x, y, t);
		return { 0, mark_s };
	}
	bool s = 1;
	score ex;
	for (int i = 0; i < 15; i++) {
		for (int j = 0; j < 15; j++) {
			if (area[i][j] && !map[i][j]) {
				if (s) {
					ex = minimax(map, { -2,0 }, i, j, 3 - t, d + 1);
					s = 0;
					if (brother.sy != -2 && ((t == 2 && scmp(brother, ex) > 0) || (t == 1 && scmp(brother, ex) < 0))) {
						tiz(map, x, y, t);
						return { -2,0 };
					}
				}
				else {
					score AI = minimax(map, ex, i, j, 3 - t, d + 1);
					if (AI.sy != -2 && ((t == 2 && scmp(AI, ex) < 0) || (t == 1 && scmp(AI, ex) > 0))) {
						ex = AI;
						if (brother.sy != -2 && ((t == 2 && scmp(brother, ex) > 0) || (t == 1 && scmp(brother, ex) < 0))) {
							tiz(map, x, y, t);
							return { -2,0 };
						}
					}
				}
			}
		}
	}
	tiz(map, x, y, t);
	return ex;
}

pos decision(int map[15][15], const int x, const int y) {
	score ex;
	pos xy;
	int t = map[x][y]; // 获取刚刚落子的颜色 (玩家落黑就是 2)
	bool s = 1;
	for (int i = 0; i < 15; i++) {
		for (int j = 0; j < 15; j++) {
			if (area[i][j] && !map[i][j]) {
				if (s) {
					ex = minimax(map, { -2,0 }, i, j, 3 - t, 1);
					xy.x = i;
					xy.y = j;
					s = 0;
				}
				else {
					score AI = minimax(map, ex, i, j, 3 - t, 1);
					if (AI.sy != -2 && ((t == 2 && scmp(AI, ex) < 0) || (t == 1 && scmp(AI, ex) > 0))) {
						xy.x = i;
						xy.y = j;
						ex = AI;
					}
				}
			}
		}
	}
	return xy;
}
// ================= 原版 AI 逻辑结束 =================

// --- SDL2 辅助渲染 ---
void DrawFilledCircle(SDL_Renderer* rend, int x0, int y0, int radius) {
	for (int w = 0; w < radius * 2; w++) {
		for (int h = 0; h < radius * 2; h++) {
			int dx = radius - w;
			int dy = radius - h;
			if ((dx * dx + dy * dy) <= (radius * radius)) {
				SDL_RenderDrawPoint(rend, x0 + dx, y0 + dy);
			}
		}
	}
}

void RenderText(const char* text, int x, int y, SDL_Color color) {
	if (!font) return;
	SDL_Surface* surface = TTF_RenderUTF8_Solid(font, text, color);
	SDL_Texture* texture = SDL_CreateTextureFromSurface(renderer, surface);
	SDL_Rect rect = { x, y, surface->w, surface->h };
	SDL_RenderCopy(renderer, texture, NULL, &rect);
	SDL_FreeSurface(surface);
	SDL_DestroyTexture(texture);
}

void print_map(const int map[15][15]) {
	SDL_SetRenderDrawColor(renderer, 255, 255, 255, 255);
	SDL_RenderClear(renderer);
	SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
	for (int ii = 100; ii <= 800; ii += 50) {
		SDL_RenderDrawLine(renderer, ii, 50, ii, 750);
		SDL_RenderDrawLine(renderer, 100, ii, 800, ii);
	}
	for (int x = 0; x < 15; x++) {
		for (int y = 0; y < 15; y++) {
			int xc = x * 50 + 100;
			int yc = y * 50 + 50;
			if (map[x][y] == 1) { // 白子
				SDL_SetRenderDrawColor(renderer, 200, 200, 200, 255);
				DrawFilledCircle(renderer, xc, yc, 20);
			}
			else if (map[x][y] == 2) { // 黑子
				SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
				DrawFilledCircle(renderer, xc, yc, 20);
			}
		}
	}
}

// --- SDL2 游戏主循环 (替代 EasyX) ---
void game_start() {
	int map[15][15] = { 0 };
	bool quit = false;
	SDL_Event e;
	
	// 状态控制：0 进行中, 1 白胜, 2 黑胜, 3 平局
	int gameState = 0; 
	int round = 0;
	bool isPlayerTurn = true; // 假设玩家执黑 (2) 先手
	int last_x = -1, last_y = -1;

	SDL_Color textColor = { 0, 0, 0, 255 };
	SDL_Color winColor = { 255, 0, 0, 255 };

	while (!quit) {
		while (SDL_PollEvent(&e) != 0) {
			if (e.type == SDL_QUIT) quit = true;
			// 仅在游戏进行中响应点击
			else if (e.type == SDL_MOUSEBUTTONDOWN && isPlayerTurn && gameState == 0) {
				int mouseX = e.button.x;
				int mouseY = e.button.y;
				for (int aa = 0; aa < 15; aa++) {
					for (int bb = 0; bb < 15; bb++) {
						if (!map[aa][bb] && mouseX > 50 * aa + 80 && mouseX < 50 * aa + 120 && mouseY > 50 * bb + 30 && mouseY < 50 * bb + 70) {
							last_x = aa;
							last_y = bb;
							loz(map, last_x, last_y, 2); // 黑棋落子
							round++;
							
							int result = check_win(map, last_x, last_y);
							if (result != 0) gameState = result;
							else if (round == 225) gameState = 3;
							else isPlayerTurn = false; // 交给 AI
							
							break;
						}
					}
					if (!isPlayerTurn || gameState != 0) break;
				}
			}
		}

		print_map(map);

		if (gameState == 0) { // 游戏进行中
			if (isPlayerTurn) {
				RenderText("你的回合 (黑棋)", 900, 450, textColor);
			} else {
				RenderText("AI 思考中...", 900, 450, textColor);
				SDL_RenderPresent(renderer); // 强制渲染提示文字

				// AI 决策 (传入玩家上一步位置以判断颜色)
				pos AI = decision(map, last_x, last_y);
				last_x = AI.x;
				last_y = AI.y;
				loz(map, last_x, last_y, 1); // 白棋落子
				round++;

				int result = check_win(map, last_x, last_y);
				if (result != 0) gameState = result;
				else if (round == 225) gameState = 3;
				else isPlayerTurn = true; // 交还给玩家
			}
		} else { // 游戏结束
			if (gameState == 1) RenderText("白棋胜！(AI赢或你触发禁手)", 850, 450, winColor);
			else if (gameState == 2) RenderText("黑棋胜！(恭喜你)", 850, 450, winColor);
			else if (gameState == 3) RenderText("平局！", 900, 450, textColor);
		}

		SDL_RenderPresent(renderer);
		SDL_Delay(16);
	}
}

int main(int argc, char* args[]) {
	// 必须执行你原版的 ran 数组边界初始化，否则 AI 评估区域全为 0 会死循环！
	for (int i = 0; i < 15; i++) {
		for (int j = 0; j < 15; j++) {
			for (int k = 0; k < 4; k++) {
				if (k == 0) {
					for (int l = -2; l < 3; l++) { ran[i][j][k][0] = l; if (j + l > 1) break; }
					for (int l = 2; l > -3; l--) { ran[i][j][k][1] = l; if (j + l < 13) break; }
				}
				else if (k == 2) {
					for (int l = -2; l < 3; l++) { ran[i][j][k][0] = l; if (i + l > 1) break; }
					for (int l = 2; l > -3; l--) { ran[i][j][k][1] = l; if (i + l < 13) break; }
				}
				else {
					for (int l = -2; l < 3; l++) { ran[i][j][k][0] = l; if (i + l * dx4[k] > 1 && i + l * dx4[k] < 13 && j + l * dy4[k] > 1 && j + l * dy4[k] < 13) break; }
					for (int l = 2; l > -3; l--) { ran[i][j][k][1] = l; if (i + l * dx4[k] > 1 && i + l * dx4[k] < 13 && j + l * dy4[k] > 1 && j + l * dy4[k] < 13) break; }
				}
			}
		}
	}

	if (SDL_Init(SDL_INIT_VIDEO) < 0 || TTF_Init() == -1) return -1;
	window = SDL_CreateWindow("Gomoku AI Benchmark", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, 1280, 960, SDL_WINDOW_SHOWN);
	renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
	font = TTF_OpenFont("simhei.ttf", 36); 
	if (!font) std::cout << "Warning: simhei.ttf not found!" << std::endl;

	game_start();

	if (font) TTF_CloseFont(font);
	SDL_DestroyRenderer(renderer);
	SDL_DestroyWindow(window);
	TTF_Quit();
	SDL_Quit();
	return 0;
}