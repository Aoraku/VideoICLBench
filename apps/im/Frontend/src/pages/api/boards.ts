// src/pages/api/boards.ts
import type { NextApiRequest, NextApiResponse } from 'next';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  // 拦截 GET 请求
  if (req.method === 'GET') {
    // 直接返回 api.md 里约定好的成功响应格式
    res.status(200).json({
      code: 0,
      info: "Succeed",
      boards: [
        {
          id: 1,
          boardName: "软件工程大作业群",
          createdAt: 1715657946.777,
          userName: "Ashitemaru",
        },
        {
          id: 2,
          boardName: "前端开发讨论组",
          createdAt: 1715658000.000,
          userName: "李沛霖",
        }
      ]
    });
  } else {
    res.status(405).json({ code: -3, info: "Bad method" });
  }
}