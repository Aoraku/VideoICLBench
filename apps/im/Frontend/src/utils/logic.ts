import { BOARD_LENGTH } from "../constants/constants";
import { Board } from "./types";

export const getBlankBoard = (): Board => Array.from(
    { length: BOARD_LENGTH },
    () => Array<0>(BOARD_LENGTH).fill(0),
);

export const boardToString = (board: Board): string => {
    return board.map((row) => row.join("")).join("");
};

export const stringToBoard = (str: string): Board => {
    if (str.length !== BOARD_LENGTH * BOARD_LENGTH) {
        throw new Error("Invalid parameter");
    }

    const board: Board = [];
    for (let i = 0; i < BOARD_LENGTH; ++i) {
        const row: (0 | 1)[] = [];
        for (let j = 0; j < BOARD_LENGTH; ++j) {
            const val = Number(str[i * BOARD_LENGTH + j]);
            if (val !== 0 && val !== 1) {
                return getBlankBoard();
            }

            row.push(val);
        }

        board.push(row);
    }

    return board;
};

export const stepBoard = (board: Board): Board => {
    const newBoard: Board = [];

    /**
     * @todo [Step 1] 请在下面两条注释之间的区域填写你的代码完成该游戏的核心逻辑
     * @note 你可以使用命令 pnpm test step 来运行我们编写的单元测试与我们提供的参考实现对拍
     */
    // Step 1 BEGIN
    for (let i = 0; i < BOARD_LENGTH; ++i) {
        for (let j = 0; j < BOARD_LENGTH; ++j) {
            let count = 0;
            for (let x = -1; x <= 1; ++x) {
                for (let y = -1; y <= 1; ++y) {
                    if (x === 0 && y === 0) {
                        continue;
                    }
                    let ni = i + x;
                    if (ni < 0) {
                        ni += BOARD_LENGTH;
                    }
                    if (ni >= BOARD_LENGTH) {
                        ni -= BOARD_LENGTH;
                    }
                    let nj = j + y;
                    if (nj < 0) {
                        nj += BOARD_LENGTH;
                    }
                    if (nj >= BOARD_LENGTH) {
                        nj -= BOARD_LENGTH;
                    }
                    count += board[ni][nj];
                }
            }
            newBoard[i] = newBoard[i] || [];
            if (board[i][j] === 1) {
                if (count === 2 || count === 3) {
                    newBoard[i][j] = 1;
                }
                else {
                    newBoard[i][j] = 0;
                }
            } else {
                if (count === 3) {
                    newBoard[i][j] = 1;
                }else {
                    newBoard[i][j] = 0;
                }
            }
        }
    }
    // Step 1 END

    return newBoard;
};

export const flipCell = (board: Board, i: number, j: number): Board => {
    /**
     * @todo [Step 3] 请在下面两条注释之间的区域填写你的代码完成切换细胞状态的任务
     * @note 你可以使用命令 pnpm test flip 来运行我们编写的单元测试以检验自己的实现
     */
    // Step 3 BEGIN
    if (i < 0 || i >= BOARD_LENGTH || j < 0 || j >= BOARD_LENGTH) {
        throw new Error("Invalid parameter");
    }
    const newBoard = board.map((row) => row.slice());
    newBoard[i][j] = newBoard[i][j] === 0 ? 1 : 0;
    return newBoard;

    // Step 3 END

    /**
     * @note 该 return 语句是为了在填入缺失代码前也不至于触发 ESLint Error
     */
    throw new Error("This line should be unreachable.");
    return board;
};
