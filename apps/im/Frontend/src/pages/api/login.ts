// src/pages/api/login.ts
import type { NextApiRequest, NextApiResponse } from 'next';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'POST') {
    const { userName, password } = req.body;

    if (password === '123456') {
      res.status(200).json({
        code: 0,
        info: "Succeed",
        token: "mock.jwt.token.abcdefg1234567" 
      });
    } else {
      res.status(401).json({
        code: 2,
        info: "Wrong password"
      });
    }
  } else {
    res.status(405).json({
      code: -3,
      info: "Bad method"
    });
  }
}