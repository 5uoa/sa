import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { loadEnvFile } from 'node:process';

const root = resolve(import.meta.dirname, '../..');

for (const path of [resolve(root, '.env'), resolve(root, 'admin', '.env')]) {
  if (existsSync(path)) loadEnvFile(path);
}

function required(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`缺少 ${name}：请在项目根 .env 配置测试账号后再运行 E2E。`);
  }
  return value;
}

export const ADMIN = {
  username: process.env.TEST_ADMIN_USERNAME || 'admin',
  password: required('TEST_ADMIN_PASSWORD'),
};

export const DEPT_USER = {
  username: process.env.TEST_USER_USERNAME || 'deptuser',
  password: process.env.TEST_USER_PASSWORD || '',
};
